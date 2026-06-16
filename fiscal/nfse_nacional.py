"""
Integração com NFS-e Nacional via API do Emissor Público.
Documentação: https://www.nfse.gov.br/EmissorNacional/api
"""
import json
import logging
import re
from datetime import datetime
from decimal import Decimal

import requests

from fiscal.nfe_status import get_certificado_path, get_senha_certificado

logger = logging.getLogger(__name__)

NFSE_API_URL = 'https://www.nfse.gov.br/EmissorNacional/api'
NFSE_HOM_URL = 'https://hom.nfse.gov.br/EmissorNacional/api'


def get_api_url(homologacao=True):
    return NFSE_HOM_URL if homologacao else NFSE_API_URL


def _limpar_documento(valor: str) -> str:
    return re.sub(r'\D', '', str(valor or ''))


def _cnpj_empresa(config_fiscal) -> str:
    cnpj = config_fiscal.cnpj or config_fiscal.loja.cnpj or config_fiscal.loja.empresa.cnpj
    return _limpar_documento(cnpj)


def _codigo_ibge_loja(config_fiscal) -> str:
    loja = config_fiscal.loja
    return (
        loja.codigo_ibge_municipio
        or loja.empresa.codigo_ibge_municipio
        or '2919207'
    )


def montar_tomador(nfse):
    tomador = {'xNome': nfse.nome_tomador}
    if nfse.cpf_cnpj_tomador:
        doc = _limpar_documento(nfse.cpf_cnpj_tomador)
        if len(doc) == 14:
            tomador['CNPJ'] = doc
        elif len(doc) == 11:
            tomador['CPF'] = doc
    if nfse.email_tomador:
        tomador['email'] = nfse.email_tomador
    return tomador


def montar_payload_nfse(nfse, config):
    """Monta o payload JSON para a API NFS-e Nacional."""
    loja = config.loja
    empresa = loja.empresa
    codigo_ibge = _codigo_ibge_loja(config)
    cidade = loja.cidade or empresa.cidade or 'Lauro de Freitas'

    return {
        'infNFSe': {
            'xLocEmi': cidade,
            'xLocPrestacao': cidade,
            'nNFSe': nfse.numero_rps,
            'cNFSe': '',
            'serie': nfse.serie_rps,
            'dhEmi': datetime.now().isoformat(),
            'tpEmit': '1',
            'cLocEmi': codigo_ibge,
            'prest': {
                'CNPJ': _cnpj_empresa(config),
                'xNome': empresa.razao_social or empresa.nome_fantasia,
                'IM': config.inscricao_municipal or '',
            },
            'toma': montar_tomador(nfse),
            'serv': {
                'cServ': {
                    'cTribNac': nfse.codigo_servico,
                    'xDescServ': nfse.discriminacao,
                },
                'cLocIncid': nfse.municipio_prestacao or codigo_ibge,
                'xDescServ': nfse.discriminacao,
            },
            'valores': {
                'vServPrest': {
                    'vReceb': str(nfse.valor_servico),
                    'vServ': str(nfse.valor_servico),
                },
                'trib': {
                    'tribMun': {
                        'tribISSQN': '1',
                        'cNatOp': '1',
                        'BM': {
                            'xMun': cidade,
                            'cMun': codigo_ibge,
                        },
                        'pAliq': str(nfse.aliquota_iss),
                        'vCalcDed': str(nfse.valor_deducoes),
                        'vCalcBC': str(nfse.valor_servico),
                        'vISSQN': str(nfse.valor_iss),
                        'tpRetISSQN': '1' if nfse.iss_retido else '2',
                    },
                    'totTrib': {
                        'vTotTrib': {
                            'vTotTribFed': '0.00',
                            'vTotTribEst': '0.00',
                            'vTotTribMun': str(nfse.valor_iss),
                        }
                    },
                },
            },
        }
    }


def calcular_valores_nfse(nfse) -> None:
    """Calcula ISS e valor líquido antes do envio."""
    base = nfse.valor_servico - nfse.valor_deducoes
    if base < 0:
        base = Decimal('0.00')
    nfse.valor_iss = (base * nfse.aliquota_iss).quantize(Decimal('0.01'))
    nfse.valor_liquido = nfse.valor_servico - nfse.valor_iss
    nfse.save(update_fields=['valor_iss', 'valor_liquido', 'updated_at'])


def processar_resposta_nfse(nfse, response):
    """Processa retorno da API e atualiza o model."""
    if response.status_code == 200:
        try:
            data = response.json()
        except json.JSONDecodeError:
            data = {'raw': response.text}
        nfse.status = 'AUTORIZADA'
        nfse.numero = data.get('nNFSe') or nfse.numero
        nfse.codigo_verificacao = data.get('cVerifNFSe', '')
        nfse.link_nfse = data.get('linkNFSe', '')
        nfse.xml_retorno = json.dumps(data, ensure_ascii=False)
        nfse.data_emissao = datetime.now()
        nfse.motivo_rejeicao = ''
        nfse.save()
        return {'sucesso': True, 'numero': nfse.numero}

    nfse.status = 'REJEITADA'
    nfse.motivo_rejeicao = response.text[:2000]
    nfse.xml_retorno = response.text[:5000]
    nfse.save()
    return {'sucesso': False, 'erro': response.text}


def emitir_nfse(nfse, config_fiscal):
    """
    Emite NFS-e via API do Emissor Público Nacional.
    Usa certificado A1 (.pfx) para autenticação mTLS quando disponível.
    """
    homologacao = config_fiscal.ambiente == 'HOMOLOGACAO'
    url = get_api_url(homologacao)
    calcular_valores_nfse(nfse)

    payload = montar_payload_nfse(nfse, config_fiscal)
    nfse.xml_enviado = json.dumps(payload, ensure_ascii=False)
    nfse.status = 'ENVIADA'
    nfse.save(update_fields=['xml_enviado', 'status', 'updated_at'])

    cert_kwargs = {}
    try:
        certificado_path = get_certificado_path(config_fiscal)
        cert_kwargs['cert'] = certificado_path
    except ValueError as exc:
        logger.warning('NFS-e sem certificado mTLS: %s', exc)

    try:
        response = requests.post(
            f'{url}/v1/nfse',
            json=payload,
            timeout=30,
            **cert_kwargs,
        )
    except requests.RequestException as exc:
        nfse.status = 'REJEITADA'
        nfse.motivo_rejeicao = str(exc)
        nfse.save(update_fields=['status', 'motivo_rejeicao', 'updated_at'])
        return {'sucesso': False, 'erro': str(exc)}

    return processar_resposta_nfse(nfse, response)


def cancelar_nfse(nfse, motivo: str) -> dict:
    """Cancela NFS-e autorizada (registro local; API em etapa futura)."""
    if nfse.status != 'AUTORIZADA':
        raise ValueError('Somente NFS-e autorizada pode ser cancelada.')
    nfse.status = 'CANCELADA'
    nfse.motivo_rejeicao = motivo.strip()
    nfse.save(update_fields=['status', 'motivo_rejeicao', 'updated_at'])
    return {'cancelada': True, 'mensagem': 'NFS-e cancelada no sistema.'}
