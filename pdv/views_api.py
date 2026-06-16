"""
Views API do app pdv.
"""
import json
from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from rest_framework import viewsets
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.core.exceptions import ValidationError

from core.tenant import get_empresa_ativa
from produtos.models import Produto
from produtos.utils import (
    buscar_produto_por_codigo,
    buscar_produtos_por_termo,
    preco_venda_para_json,
)
from vendas.models import PedidoVenda
from vendas.services import efetivar_pedido_tablet
from .models import CaixaSessao, Pagamento
from .serializers import CaixaSessaoSerializer, PagamentoSerializer


class CaixaSessaoViewSet(viewsets.ModelViewSet):
    queryset = CaixaSessao.objects.all()
    serializer_class = CaixaSessaoSerializer


class PagamentoViewSet(viewsets.ModelViewSet):
    queryset = Pagamento.objects.all()
    serializer_class = PagamentoSerializer


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def buscar_produtos_pdv(request):
    """
    API para buscar produtos no PDV.
    GET /api/v1/pdv/produtos/?q=termo
    Suporta código de barras principal/alternativo.
    """
    termo = request.query_params.get('q', '').strip()

    if not termo:
        return Response({'erro': 'Parâmetro q é obrigatório'}, status=400)

    empresa_ctx = get_empresa_ativa(request)

    if termo.isdigit() and len(termo) >= 8:
        produto, codigo_alt, mult = buscar_produto_por_codigo(termo, empresa=empresa_ctx)
        if produto:
            resultados = [{
                'id': produto.id,
                'codigo_interno': produto.codigo_interno,
                'codigo_barras': termo,
                'descricao': produto.descricao,
                'preco_venda_sugerido': preco_venda_para_json(produto, empresa_ctx),
                'unidade_comercial': produto.unidade_comercial,
                'possui_restricao_exercito': produto.possui_restricao_exercito,
                'classe_risco': produto.classe_risco,
                'multiplicador': float(mult),
                'info_codigo': codigo_alt.descricao if codigo_alt else None,
                'codigo_alternativo_id': codigo_alt.id if codigo_alt else None,
            }]
            return Response({'produtos': resultados})

    produtos = buscar_produtos_por_termo(termo, empresa=empresa_ctx, limit=20)
    resultados = []
    for p in produtos:
        resultados.append({
            'id': p.id,
            'codigo_interno': p.codigo_interno,
            'codigo_barras': p.codigo_barras or '',
            'descricao': p.descricao,
            'preco_venda_sugerido': preco_venda_para_json(p, empresa_ctx),
            'unidade_comercial': p.unidade_comercial,
            'possui_restricao_exercito': p.possui_restricao_exercito,
            'classe_risco': p.classe_risco,
            'multiplicador': 1.0,
            'info_codigo': None,
            'codigo_alternativo_id': None,
        })
    return Response({'produtos': resultados})


# ---------------------------------------------------------------------------
# APIs para efetivar pedidos do tablet no balcão (/pdv/api/...)
# ---------------------------------------------------------------------------


@login_required
@require_http_methods(['GET'])
def buscar_pedido_tablet(request):
    """
    Busca pedido do tablet para efetivar no balcão.
    GET /pdv/api/buscar-pedido-tablet/?numero=<id>
    """
    numero = request.GET.get('numero', '').strip()
    if not numero:
        return JsonResponse({'erro': 'Número do pedido é obrigatório'}, status=400)
    try:
        pedido_id = int(numero.lstrip('0') or '0')
    except (ValueError, TypeError):
        return JsonResponse({'erro': 'Número do pedido inválido'}, status=400)
    if pedido_id <= 0:
        return JsonResponse({'erro': 'Número do pedido inválido'}, status=400)

    pedido = (
        PedidoVenda.objects.filter(
            id=pedido_id,
            origem='TABLET',
            status='AGUARDANDO_PAGAMENTO',
            is_active=True,
        )
        .select_related('cliente', 'loja', 'atendente_tablet__user')
        .prefetch_related('itens__produto')
        .first()
    )
    if not pedido:
        return JsonResponse(
            {'erro': 'Pedido não encontrado, já foi finalizado ou não é do tablet.'},
            status=404,
        )

    itens = []
    for item in pedido.itens.filter(is_active=True):
        itens.append({
            'produto': item.produto.descricao,
            'codigo': getattr(item.produto, 'codigo_interno', '') or '',
            'quantidade': float(item.quantidade),
            'preco_unitario': float(item.preco_unitario),
            'total': float(item.total),
        })

    forma = getattr(pedido, 'forma_pagamento_pretendida', None) or 'NAO_INFORMADO'
    display = getattr(pedido, 'get_forma_pagamento_pretendida_display', None)
    forma_label = display() if callable(display) else forma

    return JsonResponse({
        'id': pedido.id,
        'numero': f'{pedido.id:04d}',
        'cliente': {
            'id': pedido.cliente_id,
            'nome': pedido.cliente.nome_razao_social if pedido.cliente else 'Sem cliente',
        } if pedido.cliente else None,
        'atendente': (
            pedido.atendente_tablet.user.get_full_name() or pedido.atendente_tablet.user.username
            if pedido.atendente_tablet and hasattr(pedido.atendente_tablet, 'user')
            else 'Sem atendente'
        ),
        'valor_total': float(pedido.valor_total),
        'forma_pagamento_pretendida': forma,
        'forma_pagamento_pretendida_label': forma_label,
        'itens': itens,
        'created_at': pedido.created_at.strftime('%d/%m/%Y %H:%M') if pedido.created_at else '',
    })


@login_required
@require_http_methods(['POST'])
def efetivar_pedido_tablet_view(request):
    """
    Efetiva pedido do tablet no balcão.
    POST /pdv/api/efetivar-pedido-tablet/
    Body: pedido_id, caixa_sessao_id, tipo_pagamento; valor_recebido (DINHEIRO), observacoes opcionais.
    """
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'erro': 'JSON inválido'}, status=400)

    pedido_id = data.get('pedido_id')
    caixa_sessao_id = data.get('caixa_sessao_id')
    tipo_pagamento = data.get('tipo_pagamento')
    if not all([pedido_id is not None, caixa_sessao_id is not None, tipo_pagamento]):
        return JsonResponse(
            {'erro': 'Campos obrigatórios: pedido_id, caixa_sessao_id, tipo_pagamento'},
            status=400,
        )

    valor_recebido = data.get('valor_recebido')
    if valor_recebido is not None:
        try:
            valor_recebido = Decimal(str(valor_recebido))
        except (ValueError, TypeError):
            return JsonResponse({'erro': 'Valor recebido inválido'}, status=400)

    observacoes = data.get('observacoes')
    emitir_cupom_fiscal = bool(data.get('emitir_cupom_fiscal', False))
    cpf_cnpj_nota = data.get('cpf_cnpj_nota')
    if cpf_cnpj_nota:
        cpf_cnpj_nota = ''.join(filter(str.isdigit, str(cpf_cnpj_nota))) or None

    try:
        resultado = efetivar_pedido_tablet(
            pedido_id=int(pedido_id),
            caixa_sessao_id=int(caixa_sessao_id),
            usuario=request.user,
            tipo_pagamento=str(tipo_pagamento).strip(),
            valor_recebido=valor_recebido,
            observacoes=observacoes,
            emitir_cupom_fiscal=emitir_cupom_fiscal,
            cpf_cnpj_nota=cpf_cnpj_nota,
        )
        return JsonResponse({
            **resultado,
            'cupom_fiscal_emitido': emitir_cupom_fiscal,
            'numero_cupom': resultado.get('numero_cupom'),
        })
    except ValidationError as e:
        return JsonResponse({'erro': str(e)}, status=400)
    except Exception as e:
        return JsonResponse({'erro': f'Erro ao efetivar pedido: {str(e)}'}, status=500)


@login_required
@require_http_methods(['GET'])
def verificar_caixa_aberto(request):
    """
    Verifica se há caixa aberto para o usuário.
    GET /pdv/api/verificar-caixa/
    """
    caixa = (
        CaixaSessao.objects.filter(
            usuario_abertura=request.user,
            status='ABERTO',
            is_active=True,
        )
        .select_related('loja')
        .first()
    )
    if caixa:
        return JsonResponse({
            'caixa_aberto': True,
            'caixa_sessao_id': caixa.id,
            'loja': {'id': caixa.loja_id, 'nome': caixa.loja.nome},
            'valor_inicial': float(caixa.saldo_inicial),
            'data_abertura': caixa.data_hora_abertura.strftime('%d/%m/%Y %H:%M'),
        })
    return JsonResponse({
        'caixa_aberto': False,
        'erro': 'Nenhum caixa aberto. Abra o caixa para realizar vendas.',
    })
