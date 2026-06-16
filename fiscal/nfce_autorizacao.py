"""
Autorização de NFC-e modelo 65 via PyNFe.
Reutiliza a mesma infraestrutura da NF-e modelo 55.
"""
import logging
from decimal import Decimal

from django.utils import timezone
from lxml import etree

from fiscal.nfe_autorizacao import _find_inf_prot, _parse_resposta_bruta, _text_inf_prot
from fiscal.nfe_status import get_certificado_path, get_senha_certificado

logger = logging.getLogger(__name__)


def gerar_xml_nfce(nfce, config):
    """
    Gera o XML da NFC-e no padrão modelo 65.

    TODO: integrar com PyNFe SerializacaoXML (modelo 65, indPag, CSC/QR Code).
    Por ora monta envelope mínimo para fluxo de autorização.
    """
    if not nfce.itens.filter(is_active=True).exists():
        raise ValueError('NFC-e deve ter pelo menos um item ativo.')

    itens_xml = []
    for idx, item in enumerate(nfce.itens.filter(is_active=True).order_by('id'), start=1):
        itens_xml.append(
            f'<det nItem="{idx}">'
            f'<prod><cProd>{item.produto_id}</cProd>'
            f'<xProd>{item.descricao}</xProd>'
            f'<NCM>{item.ncm or ""}</NCM>'
            f'<CFOP>{item.cfop}</CFOP>'
            f'<qCom>{item.quantidade}</qCom>'
            f'<vUnCom>{item.valor_unitario}</vUnCom>'
            f'<vProd>{item.valor_total}</vProd></prod></det>'
        )

    ambiente = '2' if nfce.ambiente == 'HOMOLOGACAO' else '1'
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<NFe xmlns="http://www.portalfiscal.inf.br/nfe">'
        '<infNFe versao="4.00">'
        f'<ide><mod>65</mod><serie>{nfce.serie}</serie><nNF>{nfce.numero}</nNF>'
        f'<tpAmb>{ambiente}</tpAmb></ide>'
        f'<total><ICMSTot><vNF>{nfce.valor_total}</vNF></ICMSTot></total>'
        f'{"".join(itens_xml)}'
        '</infNFe></NFe>'
    )
    return xml


def processar_resposta_nfce(nfce, resposta: dict) -> dict:
    """Processa retorno da SEFAZ e atualiza o model."""
    autorizada = resposta.get('autorizada', False)
    cstat = resposta.get('cStat', '')
    xmotivo = resposta.get('xMotivo', '')

    if autorizada:
        nfce.status = 'AUTORIZADA'
        nfce.chave_acesso = resposta.get('chNFe', '') or nfce.chave_acesso
        nfce.protocolo = resposta.get('nProt', '')
        nfce.data_autorizacao = timezone.now()
        nfce.xml_retorno = resposta.get('xml_proc', '') or nfce.xml_retorno
        nfce.motivo_rejeicao = ''
    else:
        nfce.status = 'REJEITADA'
        nfce.motivo_rejeicao = f'cStat {cstat}: {xmotivo}'

    nfce.save()
    return {
        'sucesso': autorizada,
        'autorizada': autorizada,
        'cStat': cstat,
        'xMotivo': xmotivo,
        'chNFe': resposta.get('chNFe', ''),
        'nProt': resposta.get('nProt', ''),
    }


def _enviar_xml_nfce_sefaz(nfce, xml_text: str, config) -> dict:
    """Envia XML assinado da NFC-e para autorização síncrona."""
    from pynfe.processamento.comunicacao import ComunicacaoSefaz

    homologacao = config.ambiente == 'HOMOLOGACAO'
    certificado_path = get_certificado_path(config)
    senha = get_senha_certificado(config)

    con = ComunicacaoSefaz(
        uf='ba',
        certificado=certificado_path,
        certificado_senha=senha,
        homologacao=homologacao,
    )

    if isinstance(xml_text, bytes):
        xml_text = xml_text.decode('utf-8', errors='replace')

    try:
        nfe_element = etree.fromstring(xml_text.encode('utf-8'))
    except Exception as exc:
        raise ValueError(f'XML da NFC-e inválido: {exc}') from exc

    logger.info(
        'Enviando NFC-e %s/%s para SEFAZ-BA (ambiente=%s)',
        nfce.numero,
        nfce.serie,
        config.ambiente,
    )

    try:
        retorno_py = con.autorizacao(
            modelo='nfce',
            nota_fiscal=nfe_element,
            id_lote=nfce.id,
            ind_sinc=1,
        )
    except Exception as exc:
        logger.exception('Erro de comunicação SEFAZ (NFC-e): %s', exc)
        return {
            'autorizada': False,
            'cStat': '999',
            'xMotivo': f'Erro de comunicação: {exc}',
            'chNFe': '',
            'nProt': '',
            'xml_proc': '',
        }

    if not isinstance(retorno_py, tuple) or len(retorno_py) < 2:
        return {
            'autorizada': False,
            'cStat': '999',
            'xMotivo': 'Resposta inesperada do PyNFe.',
            'chNFe': '',
            'nProt': '',
            'xml_proc': '',
        }

    code = retorno_py[0]
    if code == 0 and len(retorno_py) >= 2:
        proc_el = retorno_py[1]
        if isinstance(proc_el, etree._Element):
            xml_proc_str = etree.tostring(proc_el, encoding='unicode', pretty_print=False)
            inf_prot = _find_inf_prot(proc_el)
            parsed = _text_inf_prot(inf_prot) if inf_prot is not None else {}
            cstat = parsed.get('cStat', '')
            autorizada = cstat in ('100', '150')
            return {
                'autorizada': autorizada,
                'cStat': cstat or ('100' if autorizada else ''),
                'xMotivo': parsed.get('xMotivo', ''),
                'chNFe': parsed.get('chNFe', ''),
                'nProt': parsed.get('nProt', ''),
                'xml_proc': xml_proc_str,
            }

    resp = retorno_py[1]
    if hasattr(resp, 'content'):
        raw = resp.content
    elif isinstance(resp, str):
        raw = resp.encode('utf-8', errors='replace')
    elif isinstance(resp, bytes):
        raw = resp
    else:
        raw = str(resp).encode('utf-8', errors='replace')

    resultado = _parse_resposta_bruta(raw)
    cstat = resultado['cStat'] or '999'
    return {
        'autorizada': cstat in ('100', '150'),
        'cStat': cstat,
        'xMotivo': resultado['xMotivo'] or 'Rejeição ou erro no processamento',
        'chNFe': resultado['chNFe'],
        'nProt': resultado['nProt'],
        'xml_proc': '',
    }


def autorizar_nfce(nfce):
    """Autoriza uma NFC-e na SEFAZ."""
    try:
        config = nfce.loja.configuracao_fiscal
    except Exception as exc:
        raise ValueError(f'Configuração fiscal da loja não encontrada: {exc}') from exc

    if nfce.status not in ('RASCUNHO', 'EM_PROCESSAMENTO', 'REJEITADA'):
        raise ValueError(
            f'NFC-e #{nfce.id} com status "{nfce.get_status_display()}" não pode ser autorizada.'
        )

    xml = nfce.xml_enviado or gerar_xml_nfce(nfce, config)
    nfce.xml_enviado = xml
    nfce.status = 'EM_PROCESSAMENTO'
    nfce.save(update_fields=['xml_enviado', 'status', 'updated_at'])

    resposta = _enviar_xml_nfce_sefaz(nfce, xml, config)
    return processar_resposta_nfce(nfce, resposta)


def cancelar_nfce(nfce, justificativa: str) -> dict:
    """
    Cancela NFC-e autorizada.

    TODO: integrar evento de cancelamento SEFAZ (modelo 65).
    """
    if nfce.status != 'AUTORIZADA':
        raise ValueError('Somente NFC-e autorizada pode ser cancelada.')
    if len(justificativa.strip()) < 15:
        raise ValueError('Justificativa deve ter no mínimo 15 caracteres.')

    nfce.status = 'CANCELADA'
    nfce.motivo_rejeicao = justificativa.strip()
    nfce.save(update_fields=['status', 'motivo_rejeicao', 'updated_at'])
    return {'cancelada': True, 'mensagem': 'NFC-e cancelada no sistema.'}


def recalcular_totais_nfce(nfce) -> None:
    """Recalcula totais da NFC-e a partir dos itens."""
    itens = nfce.itens.filter(is_active=True)
    valor_produtos = sum((i.valor_total for i in itens), Decimal('0.00'))
    valor_icms = sum((i.valor_icms for i in itens), Decimal('0.00'))
    nfce.valor_produtos = valor_produtos
    nfce.valor_icms = valor_icms
    nfce.valor_total = valor_produtos - nfce.valor_desconto
    nfce.save(update_fields=['valor_produtos', 'valor_icms', 'valor_total', 'updated_at'])
