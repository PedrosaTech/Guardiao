"""
Integração com NFS-e Nacional via API SEFIN (Emissor Público).
Documentação: https://www.nfse.gov.br/EmissorNacional/api
Emissão: POST {base}/SefinNacional/nfse (XML DPS assinado).
"""
import json
import logging
import re
import tempfile
from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import requests
from cryptography.hazmat.primitives.serialization import Encoding, NoEncryption, PrivateFormat
from cryptography.hazmat.primitives.serialization.pkcs12 import load_key_and_certificates
from erpbrasil.assinatura import Assinatura, Certificado
from erpbrasil.assinatura.excecoes import (
    CertificadoExpirado,
    CertificadoSenhaInvalida,
    ErroDeLeituraDeArquivo,
)
from lxml import etree
from nfelib.nfse.bindings.v1_0 import (
    Dps,
    Tccserv,
    TcinfDps,
    TcinfoPessoa,
    TcinfoPrestador,
    TcinfoTributacao,
    TcinfoValores,
    TclocPrest,
    TcregTrib,
    Tcserv,
    TctribMunicipal,
    TctribTotal,
    TcvservPrest,
)

from fiscal.nfe_status import get_certificado_path, get_senha_certificado

logger = logging.getLogger(__name__)

NFSE_API_URL = 'https://www.nfse.gov.br/EmissorNacional/api'
NFSE_HOM_URL = 'https://www.producaorestrita.nfse.gov.br'
NFSE_SEFIN_PROD = 'https://sefin.nfse.gov.br/SefinNacional'
NFSE_SEFIN_PATH = '/SefinNacional/nfse'
NFSE_NS = 'http://www.sped.fazenda.gov.br/nfse'


def get_api_url(homologacao=True) -> str:
    """Base URL do ambiente (homologação ou produção)."""
    if homologacao:
        return NFSE_HOM_URL
    return NFSE_SEFIN_PROD.rsplit('/SefinNacional', 1)[0]


def get_emit_url(homologacao=True) -> str:
    """URL de emissão síncrona (POST /nfse) no SEFIN Nacional."""
    return f'{get_api_url(homologacao)}{NFSE_SEFIN_PATH}'


def pfx_para_pem(config_fiscal) -> tuple[str, str]:
    """Converte certificado .pfx para arquivos PEM temporários para mTLS."""
    certificado_path = get_certificado_path(config_fiscal)
    senha = get_senha_certificado(config_fiscal)

    with open(certificado_path, 'rb') as arquivo:
        pfx_data = arquivo.read()

    chave, cert, _ = load_key_and_certificates(pfx_data, senha.encode())
    if not chave or not cert:
        raise ValueError('Certificado A1 inválido ou senha incorreta.')

    cert_pem = cert.public_bytes(Encoding.PEM)
    key_pem = chave.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption())

    tmp_cert = tempfile.NamedTemporaryFile(delete=False, suffix='.crt')
    tmp_cert.write(cert_pem)
    tmp_cert.close()

    tmp_key = tempfile.NamedTemporaryFile(delete=False, suffix='.key')
    tmp_key.write(key_pem)
    tmp_key.close()

    return tmp_cert.name, tmp_key.name


def _limpar_documento(valor: str) -> str:
    return re.sub(r'\D', '', str(valor or ''))


def _cnpj_empresa(config_fiscal) -> str:
    cnpj = config_fiscal.cnpj or config_fiscal.loja.cnpj or config_fiscal.loja.empresa.cnpj
    return _limpar_documento(cnpj).zfill(14)[-14:]


def _codigo_ibge_loja(config_fiscal) -> str:
    loja = config_fiscal.loja
    return (
        loja.codigo_ibge_municipio
        or loja.empresa.codigo_ibge_municipio
        or '2919207'
    )


def _codigo_tributacao_nacional(codigo: str) -> str:
    """Converte '01.01' ou '0101' para 6 dígitos (cTribNac)."""
    partes = [p for p in re.split(r'[.\-/]', str(codigo or '')) if p]
    if partes:
        base = ''.join(part.zfill(2) for part in partes)
        return (base + '01').zfill(6)[:6]
    return _limpar_documento(codigo).zfill(6)[:6]


def _gerar_id_dps(nfse, config) -> str:
    """
    Id da DPS: DPS + IBGE(7) + tipo inscrição(1) + CNPJ(14) + série(5) + nDPS(15).
    """
    codigo_ibge = _codigo_ibge_loja(config)
    cnpj = _cnpj_empresa(config)
    serie = (nfse.serie_rps or 'RPS')[:5].zfill(5)
    numero = str(nfse.numero_rps).zfill(15)
    id_dps = f'DPS{codigo_ibge}2{cnpj}{serie}{numero}'
    if len(id_dps) != 45:
        raise ValueError(f'Id DPS inválido ({len(id_dps)} chars): {id_dps}')
    return id_dps


def _montar_tomador_dps(nfse) -> TcinfoPessoa:
    toma = TcinfoPessoa(xNome=nfse.nome_tomador)
    if nfse.cpf_cnpj_tomador:
        doc = _limpar_documento(nfse.cpf_cnpj_tomador)
        if len(doc) == 14:
            toma.CNPJ = doc
        elif len(doc) == 11:
            toma.CPF = doc
    if nfse.email_tomador:
        toma.email = nfse.email_tomador
    return toma


def gerar_xml_dps(nfse, config) -> bytes:
    """Gera o XML DPS (Declaração de Prestação de Serviço) NFS-e Nacional v1.0."""
    loja = config.loja
    empresa = loja.empresa
    codigo_ibge = _codigo_ibge_loja(config)
    municipio_prestacao = nfse.municipio_prestacao or codigo_ibge
    now = datetime.now(ZoneInfo('America/Bahia'))
    id_dps = _gerar_id_dps(nfse, config)
    aliquota_pct = (nfse.aliquota_iss * Decimal('100')).quantize(Decimal('0.01'))

    dps = Dps(
        versao='1.00',
        infDPS=TcinfDps(
            Id=id_dps,
            tpAmb='2' if config.ambiente == 'HOMOLOGACAO' else '1',
            dhEmi=now.isoformat(timespec='seconds'),
            verAplic='GUARDIAO_1.0',
            serie=nfse.serie_rps or 'RPS',
            nDPS=str(nfse.numero_rps),
            dCompet=now.strftime('%Y-%m-%d'),
            tpEmit='1',
            cLocEmi=codigo_ibge,
            prest=TcinfoPrestador(
                CNPJ=_cnpj_empresa(config),
                IM=config.inscricao_municipal or None,
                xNome=empresa.razao_social or empresa.nome_fantasia,
                regTrib=TcregTrib(
                    opSimpNac='1',
                    regApTribSN='1',
                    regEspTrib='0',
                ),
            ),
            toma=_montar_tomador_dps(nfse),
            serv=Tcserv(
                locPrest=TclocPrest(cLocPrestacao=municipio_prestacao),
                cServ=Tccserv(
                    cTribNac=_codigo_tributacao_nacional(nfse.codigo_servico),
                    xDescServ=(nfse.discriminacao or '')[:2000],
                ),
            ),
            valores=TcinfoValores(
                vServPrest=TcvservPrest(vServ=f'{nfse.valor_servico:.2f}'),
                trib=TcinfoTributacao(
                    tribMun=TctribMunicipal(
                        tribISSQN='1',
                        pAliq=f'{aliquota_pct:.2f}',
                        tpRetISSQN='2' if nfse.iss_retido else '1',
                    ),
                    totTrib=TctribTotal(pTotTribSN='0.00'),
                ),
            ),
        ),
    )

    xml = dps.to_xml(indent='  ')
    return xml.encode('utf-8')


def assinar_xml_dps(xml_bytes: bytes, config) -> bytes:
    """Assina o XML DPS com certificado A1 (.pfx) via erpbrasil.assinatura."""
    certificado_path = get_certificado_path(config)
    senha = get_senha_certificado(config)
    certificado = Certificado(certificado_path, senha)

    root = etree.fromstring(xml_bytes)
    id_dps = root.find('.//{*}infDPS').get('Id')
    assinatura = Assinatura(certificado)
    xml_assinado = assinatura.assina_xml2(root, id_dps)

    if isinstance(xml_assinado, str):
        return xml_assinado.encode('utf-8')
    return xml_assinado


def calcular_valores_nfse(nfse) -> None:
    """Calcula ISS e valor líquido antes do envio."""
    base = nfse.valor_servico - nfse.valor_deducoes
    if base < 0:
        base = Decimal('0.00')
    nfse.valor_iss = (base * nfse.aliquota_iss).quantize(Decimal('0.01'))
    nfse.valor_liquido = nfse.valor_servico - nfse.valor_iss
    if nfse.pk:
        nfse.save(update_fields=['valor_iss', 'valor_liquido', 'updated_at'])


def _parse_resposta_api(response) -> dict:
    content_type = response.headers.get('Content-Type', '')
    if 'json' in content_type:
        try:
            return response.json()
        except json.JSONDecodeError:
            pass
    texto = response.text.strip()
    if texto.startswith('<'):
        try:
            root = etree.fromstring(response.content)
            ns = {'nfse': NFSE_NS}
            data = {'xml': texto[:5000], 'status_code': response.status_code}
            for tag in ('nNFSe', 'cVerifNFSe', 'linkNFSe', 'xMotivo'):
                el = root.find(f'.//nfse:{tag}', ns) or root.find(f'.//*[local-name()="{tag}"]')
                if el is not None and el.text:
                    data[tag] = el.text
            return data
        except etree.XMLSyntaxError:
            return {'xml': texto[:5000], 'status_code': response.status_code}
    try:
        return response.json()
    except json.JSONDecodeError:
        return {'raw': texto[:5000], 'status_code': response.status_code}


def processar_resposta_nfse(nfse, response):
    """Processa retorno da API e atualiza o model."""
    data = _parse_resposta_api(response)

    if response.status_code in (200, 201):
        nfse.status = 'AUTORIZADA'
        nfse.numero = data.get('nNFSe') or nfse.numero
        nfse.codigo_verificacao = data.get('cVerifNFSe', '')
        nfse.link_nfse = data.get('linkNFSe', '')
        nfse.xml_retorno = data.get('xml', json.dumps(data, ensure_ascii=False))[:5000]
        nfse.data_emissao = datetime.now()
        nfse.motivo_rejeicao = ''
        nfse.save()
        return {'sucesso': True, 'numero': nfse.numero, 'resposta': data}

    nfse.status = 'REJEITADA'
    erro = (
        data.get('xMotivo')
        or data.get('erro')
        or data.get('message')
        or data.get('raw')
        or response.text
    )
    nfse.motivo_rejeicao = str(erro)[:2000]
    nfse.xml_retorno = data.get('xml', json.dumps(data, ensure_ascii=False))[:5000]
    nfse.save()
    return {
        'sucesso': False,
        'status_http': response.status_code,
        'erro': str(erro)[:2000],
        'resposta': data,
    }


def emitir_nfse(nfse, config_fiscal):
    """Emite NFS-e via API SEFIN Nacional com XML DPS assinado."""
    homologacao = config_fiscal.ambiente == 'HOMOLOGACAO'
    endpoint = get_emit_url(homologacao)
    calcular_valores_nfse(nfse)

    try:
        xml_bytes = gerar_xml_dps(nfse, config_fiscal)
        xml_assinado = assinar_xml_dps(xml_bytes, config_fiscal)
    except (
        ValueError,
        OSError,
        CertificadoExpirado,
        CertificadoSenhaInvalida,
        ErroDeLeituraDeArquivo,
    ) as exc:
        logger.warning('NFS-e: falha ao gerar/assinar DPS: %s', exc)
        nfse.status = 'REJEITADA'
        nfse.motivo_rejeicao = str(exc)
        nfse.save(update_fields=['status', 'motivo_rejeicao', 'updated_at'])
        return {
            'sucesso': False,
            'erro': str(exc),
            'dica': 'Configure certificado_arquivo (.pfx) e senha_certificado na configuração fiscal.',
        }

    nfse.xml_enviado = xml_assinado.decode('utf-8')
    nfse.status = 'ENVIADA'
    nfse.save(update_fields=['xml_enviado', 'status', 'updated_at'])

    try:
        cert_pem, key_pem = pfx_para_pem(config_fiscal)
    except ValueError as exc:
        nfse.status = 'REJEITADA'
        nfse.motivo_rejeicao = str(exc)
        nfse.save(update_fields=['status', 'motivo_rejeicao', 'updated_at'])
        return {'sucesso': False, 'erro': str(exc)}

    try:
        response = requests.post(
            endpoint,
            data=xml_assinado,
            headers={'Content-Type': 'application/xml; charset=utf-8'},
            cert=(cert_pem, key_pem),
            timeout=30,
        )
    except requests.RequestException as exc:
        nfse.status = 'REJEITADA'
        nfse.motivo_rejeicao = str(exc)
        nfse.save(update_fields=['status', 'motivo_rejeicao', 'updated_at'])
        return {'sucesso': False, 'erro': str(exc)}

    return processar_resposta_nfse(nfse, response)


def cancelar_nfse(nfse, motivo: str) -> dict:
    """Cancela NFS-e autorizada (registro local; API de cancelamento em etapa futura)."""
    if nfse.status != 'AUTORIZADA':
        raise ValueError('Somente NFS-e autorizada pode ser cancelada.')
    nfse.status = 'CANCELADA'
    nfse.motivo_rejeicao = motivo.strip()
    nfse.save(update_fields=['status', 'motivo_rejeicao', 'updated_at'])
    return {'cancelada': True, 'mensagem': 'NFS-e cancelada no sistema.'}
