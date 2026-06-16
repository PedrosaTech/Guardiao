"""
Views do módulo PDV.
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import Http404, HttpResponse, JsonResponse
from django.views.decorators.http import require_http_methods
from django.db import transaction
from django.db.models import Q, Sum
from django.utils import timezone
from django.template.loader import render_to_string
from decimal import Decimal
from datetime import timedelta
import json
import logging

from core.models import Loja
from core.tenant import get_empresa_ativa
from produtos.models import Produto
from produtos.utils import (
    buscar_produto_por_codigo,
    buscar_produtos_por_termo,
    preco_venda_para_json,
    preco_venda_para_empresa,
)
from pessoas.models import Cliente
from vendas.models import CondicaoPagamento
from vendas.models import PedidoVenda
from vendas.services import criar_pedido_venda_balcao
from .models import CaixaSessao, Pagamento

logger = logging.getLogger(__name__)


def _loja_sessao(request):
    """Primeira loja da empresa ativa na sessão."""
    empresa = get_empresa_ativa(request)
    return Loja.objects.filter(empresa=empresa, is_active=True).first()


try:
    from weasyprint import HTML
    WEASYPRINT_AVAILABLE = True
except ImportError:
    WEASYPRINT_AVAILABLE = False


@login_required
def pdv_view(request):
    """
    Tela principal do PDV.
    
    LGPD: Não exibir dados sensíveis do cliente desnecessariamente na tela do PDV.
    """
    # TODO: Obter loja do usuário ou da sessão
    # Por enquanto, pega a primeira loja (ajustar conforme necessidade)
    loja = _loja_sessao(request)

    if not loja:
        return render(request, 'pdv/erro.html', {
            'mensagem': 'Nenhuma loja cadastrada para a empresa ativa. Cadastre uma loja ou troque de empresa.'
        })
    
    # Verifica se há sessão de caixa aberta
    # TODO: Futura tela de "Abrir Caixa" / "Fechar Caixa"
    caixa_aberto = CaixaSessao.objects.filter(
        loja=loja,
        status='ABERTO',
        usuario_abertura=request.user
    ).order_by('-data_hora_abertura').first()
    
    # Formas de pagamento disponíveis
    formas_pagamento = Pagamento.TIPO_CHOICES

    context = {
        'loja': loja,
        'caixa_aberto': caixa_aberto,
        'caixa_sessao_id': caixa_aberto.id if caixa_aberto else None,
        'formas_pagamento': formas_pagamento,
    }
    return render(request, 'pdv/pdv.html', context)


@login_required
def abrir_caixa(request):
    """
    Tela para abrir uma nova sessão de caixa.
    """
    # Busca loja (por enquanto pega a primeira)
    loja = _loja_sessao(request)

    if not loja:
        messages.error(
            request,
            'Nenhuma loja cadastrada para a empresa ativa.',
        )
        return redirect('pdv:pdv')

    # Verifica se já existe caixa aberto para este usuário
    caixa_aberto = CaixaSessao.objects.filter(
        loja=loja,
        status='ABERTO',
        usuario_abertura=request.user
    ).order_by('-data_hora_abertura').first()
    
    if caixa_aberto:
        messages.warning(request, f'Você já possui um caixa aberto desde {caixa_aberto.data_hora_abertura.strftime("%d/%m/%Y %H:%M")}.')
        return redirect('pdv:pdv')
    
    if request.method == 'POST':
        try:
            saldo_inicial = Decimal(request.POST.get('saldo_inicial', '0.00'))
            
            if saldo_inicial < 0:
                messages.error(request, 'O saldo inicial não pode ser negativo.')
                return render(request, 'pdv/abrir_caixa.html', {'loja': loja})
            
            # Cria nova sessão de caixa
            caixa = CaixaSessao.objects.create(
                loja=loja,
                usuario_abertura=request.user,
                saldo_inicial=saldo_inicial,
                status='ABERTO',
                created_by=request.user
            )
            
            messages.success(request, f'Caixa aberto com sucesso! Saldo inicial: R$ {saldo_inicial:.2f}')
            return redirect('pdv:pdv')
            
        except Exception as e:
            logger.error(f"Erro ao abrir caixa: {str(e)}", exc_info=True)
            messages.error(request, f'Erro ao abrir caixa: {str(e)}')
    
    context = {
        'loja': loja,
    }
    return render(request, 'pdv/abrir_caixa.html', context)


@login_required
def fechar_caixa(request, caixa_id=None):
    """
    Tela para fechar uma sessão de caixa.
    """
    # Busca loja
    loja = _loja_sessao(request)

    if not loja:
        messages.error(request, 'Nenhuma loja cadastrada para a empresa ativa.')
        return redirect('pdv:pdv')

    # Se não informou caixa_id, busca o caixa aberto do usuário
    if caixa_id:
        caixa = get_object_or_404(CaixaSessao, id=caixa_id, loja=loja, usuario_abertura=request.user)
    else:
        caixa = CaixaSessao.objects.filter(
            loja=loja,
            status='ABERTO',
            usuario_abertura=request.user
        ).order_by('-data_hora_abertura').first()
    
    if not caixa:
        messages.error(request, 'Nenhum caixa aberto encontrado.')
        return redirect('pdv:pdv')
    
    if caixa.status != 'ABERTO':
        messages.error(request, 'Este caixa já está fechado.')
        return redirect('pdv:pdv')
    
    # Calcula totais
    pagamentos = Pagamento.objects.filter(caixa_sessao=caixa)
    total_recebido = pagamentos.aggregate(Sum('valor'))['valor__sum'] or Decimal('0.00')
    
    # Saldo esperado = saldo inicial + total recebido
    saldo_esperado = caixa.saldo_inicial + total_recebido
    
    if request.method == 'POST':
        try:
            saldo_final_informado = Decimal(request.POST.get('saldo_final', '0.00'))
            
            if saldo_final_informado < 0:
                messages.error(request, 'O saldo final não pode ser negativo.')
                return render(request, 'pdv/fechar_caixa.html', {
                    'caixa': caixa,
                    'loja': loja,
                    'total_recebido': total_recebido,
                    'saldo_esperado': saldo_esperado,
                })
            
            # Fecha o caixa
            caixa.saldo_final = saldo_final_informado
            caixa.data_hora_fechamento = timezone.now()
            caixa.usuario_fechamento = request.user
            caixa.status = 'FECHADO'
            caixa.updated_by = request.user
            caixa.save()
            
            # Calcula diferença
            diferenca = saldo_final_informado - saldo_esperado
            
            messages.success(request, f'Caixa fechado com sucesso!')
            if diferenca != 0:
                if diferenca > 0:
                    messages.info(request, f'Diferença (sobra): R$ {diferenca:.2f}')
                else:
                    messages.warning(request, f'Diferença (falta): R$ {abs(diferenca):.2f}')
            
            return redirect('pdv:pdv')
            
        except Exception as e:
            logger.error(f"Erro ao fechar caixa: {str(e)}", exc_info=True)
            messages.error(request, f'Erro ao fechar caixa: {str(e)}')
    
    # Calcula diferença (se já tiver saldo final informado)
    diferenca = None
    diferenca_abs = None
    if caixa.saldo_final:
        diferenca = caixa.saldo_final - saldo_esperado
        diferenca_abs = abs(diferenca)
    
    context = {
        'caixa': caixa,
        'loja': loja,
        'total_recebido': total_recebido,
        'saldo_esperado': saldo_esperado,
        'diferenca': diferenca,
        'diferenca_abs': diferenca_abs,
        'pagamentos': pagamentos,
    }
    return render(request, 'pdv/fechar_caixa.html', context)


@login_required
@require_http_methods(["GET"])
def buscar_produto(request):
    """
    Busca produto por código de barras (principal/alternativo), código interno ou descrição.
    Usado pela API do PDV. Suporta códigos alternativos.
    """
    termo = request.GET.get('q', '').strip()

    if not termo:
        return JsonResponse({'erro': 'Termo de busca não informado'}, status=400)

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
                'multiplicador': float(mult),
                'info_codigo': codigo_alt.descricao if codigo_alt else None,
                'codigo_alternativo_id': codigo_alt.id if codigo_alt else None,
            }]
            return JsonResponse({'produtos': resultados})

    produtos = buscar_produtos_por_termo(termo, empresa=empresa_ctx, limit=10)
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
            'multiplicador': 1.0,
            'info_codigo': None,
            'codigo_alternativo_id': None,
        })
    return JsonResponse({'produtos': resultados})


@login_required
@require_http_methods(["POST"])
def criar_orcamento_pdv(request):
    """
    Cria um orçamento a partir dos itens do PDV.
    """
    try:
        data = json.loads(request.body)
        
        # Validações básicas
        loja_id = data.get('loja_id')
        itens = data.get('itens', [])
        nome_responsavel = data.get('nome_responsavel', 'Cliente Balcão')
        cliente_id = data.get('cliente_id')
        
        if not loja_id:
            return JsonResponse({'erro': 'Loja não informada'}, status=400)
        
        if not itens:
            return JsonResponse({'erro': 'O orçamento deve ter pelo menos um item'}, status=400)
        
        empresa_at = get_empresa_ativa(request)
        try:
            loja = Loja.objects.get(id=loja_id, empresa=empresa_at, is_active=True)
        except Loja.DoesNotExist:
            return JsonResponse({'erro': 'Loja não encontrada'}, status=404)

        # Cliente (opcional)
        cliente = None
        if cliente_id:
            try:
                cliente = Cliente.objects.get(
                    id=cliente_id,
                    empresa=empresa_at,
                    is_active=True,
                )
            except Cliente.DoesNotExist:
                logger.warning(f"Cliente {cliente_id} não encontrado, continuando sem cliente")

        # Valida itens
        itens_validos = []
        for item in itens:
            produto_id = item.get('produto_id')
            quantidade = item.get('quantidade')

            if not produto_id or not quantidade:
                return JsonResponse({'erro': 'Item inválido: produto_id e quantidade são obrigatórios'}, status=400)

            produto = (
                Produto.objects.filter(
                    id=produto_id,
                    is_active=True,
                    parametros_por_empresa__empresa=empresa_at,
                    parametros_por_empresa__ativo_nessa_empresa=True,
                )
                .first()
            )
            if not produto:
                return JsonResponse({'erro': f'Produto {produto_id} não encontrado'}, status=404)

            preco_unitario = Decimal(str(item.get('preco_unitario', 0)))
            if preco_unitario == 0:
                pv = preco_venda_para_empresa(produto, loja.empresa)
                if pv is None:
                    return JsonResponse({
                        'erro': f'Produto {produto.codigo_interno} sem preço para a empresa da loja.',
                    }, status=400)
                preco_unitario = pv
            desconto = Decimal(str(item.get('desconto', 0)))
            
            itens_validos.append({
                'produto': produto,
                'quantidade': Decimal(str(quantidade)),
                'valor_unitario': preco_unitario,
                'desconto': desconto,
            })
        
        # Cria o orçamento
        from orcamentos.models import OrcamentoVenda, ItemOrcamentoVenda
        
        with transaction.atomic():
            # Data de validade padrão: 30 dias
            data_validade = timezone.now().date() + timedelta(days=30)
            
            orcamento = OrcamentoVenda.objects.create(
                empresa=loja.empresa,
                loja=loja,
                cliente=cliente,
                vendedor=request.user,
                nome_responsavel=nome_responsavel,
                origem=OrcamentoVenda.OrigemChoices.BALCAO,
                tipo_operacao=OrcamentoVenda.TipoOperacaoChoices.VAREJO,
                data_validade=data_validade,
                status=OrcamentoVenda.StatusChoices.RASCUNHO,
                created_by=request.user,
            )
            
            # Cria os itens
            for item_data in itens_validos:
                ItemOrcamentoVenda.objects.create(
                    orcamento=orcamento,
                    produto=item_data['produto'],
                    quantidade=item_data['quantidade'],
                    valor_unitario=item_data['valor_unitario'],
                    desconto=item_data['desconto'],
                    created_by=request.user,
                )
            
            # Recalcula totais
            orcamento.recalcular_totais()
        
        logger.info(f"Orçamento criado com sucesso: Orçamento #{orcamento.id}")
        
        return JsonResponse({
            'sucesso': True,
            'orcamento_id': orcamento.id,
            'total_liquido': str(orcamento.total_liquido),
            'mensagem': f'Orçamento #{orcamento.id} criado com sucesso!'
        })
    
    except json.JSONDecodeError:
        return JsonResponse({'erro': 'Dados inválidos (JSON malformado)'}, status=400)
    except Exception as e:
        logger.error(f"Erro ao criar orçamento: {str(e)}", exc_info=True)
        return JsonResponse({'erro': f'Erro ao criar orçamento: {str(e)}'}, status=500)


@login_required
@require_http_methods(["POST"])
def finalizar_venda(request):
    """
    Finaliza uma venda no PDV.
    
    Valida se há caixa aberto e chama o serviço de criação de pedido.
    """
    logger.info("finalizar_venda: POST recebido")
    try:
        data = json.loads(request.body)

        # Validações básicas
        loja_id = data.get('loja_id')
        itens = data.get('itens', [])
        tipo_pagamento = data.get('tipo_pagamento')
        cliente_id = data.get('cliente_id')  # Opcional
        local_estoque_id = data.get('local_estoque_id')  # Opcional
        
        if not loja_id:
            return JsonResponse({'erro': 'Loja não informada'}, status=400)
        
        if not itens:
            return JsonResponse({'erro': 'A venda deve ter pelo menos um item'}, status=400)
        
        if not tipo_pagamento:
            return JsonResponse({'erro': 'Tipo de pagamento não informado'}, status=400)
        
        # Valida tipo de pagamento
        tipos_validos = [choice[0] for choice in Pagamento.TIPO_CHOICES]
        if tipo_pagamento not in tipos_validos:
            return JsonResponse({'erro': 'Tipo de pagamento inválido'}, status=400)
        
        empresa_at = get_empresa_ativa(request)
        try:
            loja = Loja.objects.get(id=loja_id, empresa=empresa_at, is_active=True)
        except Loja.DoesNotExist:
            return JsonResponse({'erro': 'Loja não encontrada'}, status=404)

        # Verifica se há caixa aberto
        caixa_sessao = CaixaSessao.objects.filter(
            loja=loja,
            status='ABERTO',
            usuario_abertura=request.user
        ).order_by('-data_hora_abertura').first()
        
        if not caixa_sessao:
            return JsonResponse({
                'erro': 'Nenhuma sessão de caixa aberta. Por favor, abra uma sessão de caixa antes de realizar vendas.'
            }, status=400)
        
        # Cliente (opcional para vendas de balcão)
        cliente = None
        if cliente_id:
            try:
                cliente = Cliente.objects.get(
                    id=cliente_id,
                    empresa=empresa_at,
                    is_active=True,
                )
            except Cliente.DoesNotExist:
                # Cliente não encontrado, mas não é obrigatório para balcão
                logger.warning(f"Cliente {cliente_id} não encontrado, continuando sem cliente")

        # Local de estoque (opcional)
        local_estoque = None
        if local_estoque_id:
            try:
                from estoque.models import LocalEstoque
                local_estoque = LocalEstoque.objects.get(id=local_estoque_id, loja=loja, is_active=True)
            except Exception:
                logger.warning(f"Local de estoque {local_estoque_id} não encontrado, usando padrão")

        # Valida itens
        itens_validos = []

        for item in itens:
            produto_id = item.get('produto_id')
            quantidade = item.get('quantidade')

            if not produto_id or not quantidade:
                return JsonResponse({'erro': 'Item inválido: produto_id e quantidade são obrigatórios'}, status=400)

            produto = (
                Produto.objects.filter(
                    id=produto_id,
                    is_active=True,
                    parametros_por_empresa__empresa=empresa_at,
                    parametros_por_empresa__ativo_nessa_empresa=True,
                )
                .first()
            )
            if not produto:
                return JsonResponse({'erro': f'Produto {produto_id} não encontrado'}, status=404)

            itens_validos.append({
                'produto_id': produto_id,
                'quantidade': Decimal(str(quantidade)),
                'preco_unitario': item.get('preco_unitario'),  # Opcional
                'desconto': item.get('desconto', 0),
            })
        
        # Cria o pedido usando o serviço
        try:
            pedido = criar_pedido_venda_balcao(
                loja=loja,
                caixa_sessao=caixa_sessao,
                usuario=request.user,
                itens=itens_validos,
                tipo_pagamento=tipo_pagamento,
                cliente=cliente,
                local_estoque=local_estoque,
            )
            
            logger.info(f"Venda finalizada com sucesso: Pedido #{pedido.id}")
            
            return JsonResponse({
                'sucesso': True,
                'pedido_id': pedido.id,
                'valor_total': str(pedido.valor_total),
                'mensagem': 'Venda finalizada com sucesso!',
            })
        
        except ValueError as e:
            # Erro de validação (ex: estoque insuficiente)
            logger.warning(f"Erro ao finalizar venda: {str(e)}")
            return JsonResponse({'erro': str(e)}, status=400)
        
        except Exception as e:
            # Erro inesperado
            logger.error(f"Erro inesperado ao finalizar venda: {str(e)}", exc_info=True)
            return JsonResponse({'erro': 'Erro ao processar venda. Tente novamente.'}, status=500)
    
    except json.JSONDecodeError:
        return JsonResponse({'erro': 'Dados inválidos (JSON malformado)'}, status=400)
    except Exception as e:
        logger.error(f"Erro ao processar requisição: {str(e)}", exc_info=True)
        return JsonResponse({'erro': 'Erro ao processar requisição'}, status=500)


@login_required
@require_http_methods(["GET"])
def cupom_fiscal(request, pedido_id: int):
    """
    Exibe o cupom fiscal (tela de impressão) para um pedido.
    Usado pelo fluxo do PDV Tablet -> Balcão (window.open em nova aba).
    """
    empresa = get_empresa_ativa(request)
    pedido = get_object_or_404(
        PedidoVenda.objects.select_related('loja', 'loja__empresa', 'cliente', 'vendedor'),
        id=pedido_id,
        loja__empresa=empresa,
        is_active=True,
    )
    itens = pedido.itens.filter(is_active=True).select_related('produto')
    pagamentos = pedido.pagamentos.filter(is_active=True).order_by('created_at')

    context = {
        'pedido': pedido,
        'loja': pedido.loja,
        'empresa': pedido.loja.empresa,
        'cliente': getattr(pedido, 'cliente', None),
        'itens': itens,
        'pagamentos': pagamentos,
        'autoprint': request.GET.get('autoprint') == '1',
    }
    return render(request, 'pdv/cupom_fiscal.html', context)


@login_required
@require_http_methods(["GET"])
def cupom_fiscal_pdf(request, pedido_id: int):
    """
    Gera o PDF do cupom fiscal (WeasyPrint).
    """
    if not WEASYPRINT_AVAILABLE:
        return HttpResponse(
            '<h1>Erro: WeasyPrint não instalado</h1>'
            '<p>Para gerar PDFs, instale o weasyprint:</p>'
            '<pre>pip install weasyprint</pre>',
            status=500,
        )

    empresa = get_empresa_ativa(request)
    pedido = get_object_or_404(
        PedidoVenda.objects.select_related('loja', 'loja__empresa', 'cliente', 'vendedor'),
        id=pedido_id,
        loja__empresa=empresa,
        is_active=True,
    )
    itens = pedido.itens.filter(is_active=True).select_related('produto')
    pagamentos = pedido.pagamentos.filter(is_active=True).order_by('created_at')

    context = {
        'pedido': pedido,
        'loja': pedido.loja,
        'empresa': pedido.loja.empresa,
        'cliente': getattr(pedido, 'cliente', None),
        'itens': itens,
        'pagamentos': pagamentos,
    }

    html_string = render_to_string('pdv/cupom_fiscal_pdf.html', context)
    base_url = request.build_absolute_uri('/')
    pdf = HTML(string=html_string, base_url=base_url).write_pdf()

    response = HttpResponse(pdf, content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename="Cupom_{pedido.id}.pdf"'
    return response
