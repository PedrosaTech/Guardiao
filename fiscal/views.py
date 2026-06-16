"""
Views do módulo fiscal.
"""
import base64
import io
import logging
import re

from django.shortcuts import get_object_or_404, render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import HttpResponse, Http404, JsonResponse
from django.template.loader import render_to_string
from django.db.models import Q, Sum, Count
from django.utils import timezone
from django.views.decorators.http import require_http_methods
from datetime import datetime, timedelta
from decimal import Decimal

from .models import (
    NotaFiscalSaida,
    NotaFiscalEntrada,
    ItemNotaFiscalEntrada,
    ConfiguracaoFiscalLoja,
    AlertaNotaFiscal,
    NotaFiscalConsumidor,
    NotaFiscalServico,
)
from .forms import (
    NotaFiscalEntradaForm,
    ItemNotaFiscalEntradaFormSet,
    NotaFiscalConsumidorForm,
    NotaFiscalServicoForm,
)
from .import_nfe import parse_nfe_xml
from core.tenant import get_empresa_ativa
from core.models import Loja

logger = logging.getLogger(__name__)

try:
    from weasyprint import HTML
    WEASYPRINT_AVAILABLE = True
except (ImportError, OSError):
    WEASYPRINT_AVAILABLE = False

try:
    import qrcode
    QRCODE_AVAILABLE = True
except ImportError:
    qrcode = None  # type: ignore[misc, assignment]
    QRCODE_AVAILABLE = False


def _formatar_cnpj(valor) -> str:
    digitos = re.sub(r'\D', '', str(valor or ''))
    if len(digitos) == 14:
        return f'{digitos[:2]}.{digitos[2:5]}.{digitos[5:8]}/{digitos[8:12]}-{digitos[12:]}'
    return digitos or '-'


def _formatar_cpf_ou_cnpj(valor) -> str:
    digitos = re.sub(r'\D', '', str(valor or ''))
    if len(digitos) == 11:
        return f'{digitos[:3]}.{digitos[3:6]}.{digitos[6:9]}-{digitos[9:]}'
    if len(digitos) == 14:
        return f'{digitos[:2]}.{digitos[2:5]}.{digitos[5:8]}/{digitos[8:12]}-{digitos[12:]}'
    return digitos or '-'


def _gerar_qrcode_nfe_base64(chave_acesso: str) -> str:
    if not chave_acesso or not QRCODE_AVAILABLE:
        return ''
    url = (
        'https://www.nfe.fazenda.gov.br/portal/consultaRecaptcha.aspx'
        '?tipoConsulta=completa&tipoConteudo=XbSeqxE8pl8='
        f'&nfe={chave_acesso}'
    )
    qr = qrcode.QRCode(version=1, box_size=3, border=2)
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color='black', back_color='white')
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    return base64.b64encode(buf.getvalue()).decode('utf-8')


@login_required
def lista_notas_saida(request):
    """
    Lista de notas fiscais de saída (NF-e e NFC-e).
    """
    empresa = get_empresa_ativa(request)
    notas = NotaFiscalSaida.objects.filter(
        is_active=True,
        loja__empresa=empresa,
    ).select_related(
        'loja', 'cliente', 'pedido_venda', 'evento'
    )
    
    # Filtros
    tipo_documento_filter = request.GET.get('tipo_documento')
    status_filter = request.GET.get('status')
    loja_filter = request.GET.get('loja')
    cliente_filter = request.GET.get('cliente')
    evento_filter = request.GET.get('evento')
    data_inicio = request.GET.get('data_inicio')
    data_fim = request.GET.get('data_fim')
    search = request.GET.get('search')
    
    if tipo_documento_filter:
        notas = notas.filter(tipo_documento=tipo_documento_filter)
    if status_filter:
        notas = notas.filter(status=status_filter)
    if loja_filter:
        notas = notas.filter(loja_id=loja_filter, loja__empresa=empresa)
    if cliente_filter:
        notas = notas.filter(cliente_id=cliente_filter, cliente__empresa=empresa)
    if evento_filter:
        notas = notas.filter(evento_id=evento_filter, evento__loja__empresa=empresa)
    if data_inicio:
        try:
            data_inicio_dt = datetime.strptime(data_inicio, '%Y-%m-%d')
            notas = notas.filter(data_emissao__gte=data_inicio_dt)
        except:
            pass
    if data_fim:
        try:
            data_fim_dt = datetime.strptime(data_fim, '%Y-%m-%d') + timedelta(days=1)
            notas = notas.filter(data_emissao__lt=data_fim_dt)
        except:
            pass
    if search:
        notas = notas.filter(
            Q(numero__icontains=search) |
            Q(chave_acesso__icontains=search) |
            Q(cliente__nome_razao_social__icontains=search)
        )
    
    # Ordenação
    notas = notas.order_by('-data_emissao', '-numero')
    
    # Buscar dados para filtros
    from core.models import Loja
    from pessoas.models import Cliente
    from eventos.models import EventoVenda
    
    lojas = Loja.objects.filter(empresa=empresa, is_active=True)
    clientes = Cliente.objects.filter(empresa=empresa, is_active=True)
    eventos = EventoVenda.objects.filter(loja__empresa=empresa, is_active=True)
    
    # Estatísticas
    total_valor = notas.aggregate(Sum('valor_total'))['valor_total__sum'] or 0
    total_notas = notas.count()
    
    context = {
        'notas': notas,
        'lojas': lojas,
        'clientes': clientes,
        'eventos': eventos,
        'total_valor': total_valor,
        'total_notas': total_notas,
        'filtros': {
            'tipo_documento': tipo_documento_filter,
            'status': status_filter,
            'loja': loja_filter,
            'cliente': cliente_filter,
            'evento': evento_filter,
            'data_inicio': data_inicio,
            'data_fim': data_fim,
            'search': search,
        }
    }
    
    return render(request, 'fiscal/lista_notas_saida.html', context)


@login_required
def detalhes_nota_saida(request, nota_id):
    """
    Detalhes completos da nota fiscal de saída.
    """
    empresa = get_empresa_ativa(request)
    nota = get_object_or_404(
        NotaFiscalSaida.objects.select_related(
            'loja', 'cliente', 'pedido_venda', 'evento'
        ),
        id=nota_id,
        loja__empresa=empresa,
        is_active=True
    )
    
    # Buscar configuração fiscal
    config_fiscal = None
    try:
        config_fiscal = nota.loja.configuracao_fiscal
    except:
        pass
    
    # Obter impostos (usa snapshot se autorizada, senão calcula)
    impostos = nota.get_impostos()
    
    # Calcular impostos por item para exibição
    itens_com_impostos = []
    
    if nota.pedido_venda:
        itens = nota.pedido_venda.itens.filter(is_active=True).select_related('produto')
        
        for item in itens:
            # Se autorizada, buscar do snapshot
            if nota.status == 'AUTORIZADA' and nota.impostos_snapshot:
                item_snapshot = next(
                    (s for s in nota.impostos_snapshot if s['item_id'] == item.id),
                    None
                )
                if item_snapshot:
                    impostos_item = item_snapshot['impostos']
                    # Converter valores de volta para Decimal
                    from decimal import Decimal
                    impostos_item = {
                        k: Decimal(str(v)) if isinstance(v, (int, float)) else v
                        for k, v in impostos_item.items()
                    }
                else:
                    # Fallback: calcular
                    from fiscal.calculos import calcular_impostos_item
                    regime = config_fiscal.regime_tributario if config_fiscal else None
                    impostos_item = calcular_impostos_item(item, regime, config_fiscal)
            else:
                # Calcular em tempo real
                from fiscal.calculos import calcular_impostos_item
                regime = config_fiscal.regime_tributario if config_fiscal else None
                impostos_item = calcular_impostos_item(item, regime, config_fiscal)
            
            # Helper para descrição
            if hasattr(item, 'get_descricao'):
                descricao = item.get_descricao()
            elif item.produto:
                descricao = item.produto.descricao
            elif hasattr(item, 'servico') and item.servico:
                descricao = item.servico.nome
            else:
                descricao = 'Item'
            
            itens_com_impostos.append({
                'item': item,
                'descricao': descricao,
                'quantidade': item.quantidade,
                'valor_unitario': item.preco_unitario,
                'total': item.total,
                'impostos': impostos_item,
                'eh_produto': item.produto is not None,
                'eh_servico': hasattr(item, 'servico') and item.servico is not None,
            })
    
    context = {
        'nota': nota,
        'itens': itens_com_impostos,  # ← Agora com impostos por item
        'config_fiscal': config_fiscal,
        'impostos': impostos,  # ← Totais
    }
    
    return render(request, 'fiscal/detalhes_nota_saida.html', context)


@login_required
def gerar_xml_nota(request, nota_id):
    """Gera XML assinado da NF-e (PyNFe) e salva na nota."""
    from .services import gerar_xml_nfe_para_nota

    if not request.user.is_staff:
        raise PermissionDenied

    empresa = get_empresa_ativa(request)
    get_object_or_404(
        NotaFiscalSaida,
        pk=nota_id,
        loja__empresa=empresa,
        is_active=True,
    )

    try:
        gerar_xml_nfe_para_nota(nota_id, usuario=request.user)
        messages.success(
            request,
            'XML gerado com sucesso. A nota foi marcada como em processamento.',
        )
    except (ValueError, ValidationError) as exc:
        messages.error(request, f'Erro ao gerar XML: {exc}')
    except Exception as exc:
        messages.error(request, f'Erro inesperado: {exc}')
        logger.exception('Erro ao gerar XML da nota %s', nota_id)

    return redirect(request.META.get('HTTP_REFERER', '/'))


@login_required
def autorizar_nota(request, nota_id):
    """Envia NF-e com XML gerado para autorização na SEFAZ (síncrono)."""
    from .services import autorizar_nfe

    if not request.user.is_staff:
        raise PermissionDenied

    empresa = get_empresa_ativa(request)
    nota = get_object_or_404(
        NotaFiscalSaida,
        pk=nota_id,
        loja__empresa=empresa,
        is_active=True,
    )

    if nota.status != 'EM_PROCESSAMENTO':
        messages.warning(
            request,
            f"Nota {nota.numero}/{nota.serie} está com status “{nota.get_status_display()}”. "
            'Gere o XML primeiro (nota em processamento).',
        )
        return redirect(request.META.get('HTTP_REFERER', '/'))

    try:
        resultado = autorizar_nfe(nota.id, usuario=request.user)
        if resultado['autorizada']:
            ch = resultado.get('chNFe') or ''
            preview = (ch[:24] + '…') if len(ch) > 24 else ch
            messages.success(
                request,
                f'NF-e {nota.numero}/{nota.serie} autorizada. Chave: {preview}',
            )
        else:
            messages.error(
                request,
                f'NF-e {nota.numero}/{nota.serie} não autorizada '
                f'(cStat {resultado["cStat"]}): {resultado["xMotivo"]}',
            )
    except (ValueError, ValidationError) as exc:
        messages.error(request, str(exc))
    except Exception as exc:
        messages.error(request, f'Erro ao autorizar: {exc}')
        logger.exception('Erro ao autorizar nota %s', nota_id)

    return redirect(request.META.get('HTTP_REFERER', '/'))


@login_required
def cancelar_nota(request, nota_id):
    """
    Formulário de cancelamento (GET) e envio do evento de cancelamento à SEFAZ (POST).
    """
    from .services import cancelar_nota_fiscal

    if not request.user.is_staff:
        raise PermissionDenied

    empresa = get_empresa_ativa(request)
    nota = get_object_or_404(
        NotaFiscalSaida,
        pk=nota_id,
        loja__empresa=empresa,
        is_active=True,
    )

    if nota.tipo_documento != 'NFE' or nota.status != 'AUTORIZADA':
        messages.warning(
            request,
            f'Nota {nota.numero}/{nota.serie} não pode ser cancelada por este fluxo '
            f'(tipo ou status: {nota.get_status_display()}).',
        )
        return redirect('fiscal:lista_notas_saida')

    if request.method == 'POST':
        justificativa = request.POST.get('justificativa', '').strip()
        try:
            resultado = cancelar_nota_fiscal(
                nota.id,
                justificativa=justificativa,
                usuario=request.user,
            )
            if resultado['cancelada']:
                messages.success(
                    request,
                    f'NF-e {nota.numero}/{nota.serie} cancelada com sucesso.',
                )
                return redirect('fiscal:lista_notas_saida')
            messages.error(
                request,
                f'Falha no cancelamento: cStat={resultado["cStat"]} — {resultado["xMotivo"]}',
            )
        except (ValueError, ValidationError) as exc:
            messages.error(request, str(exc))
        except Exception as exc:
            messages.error(request, f'Erro inesperado: {exc}')
            logger.exception('Erro ao cancelar nota %s', nota_id)

    return render(request, 'fiscal/cancelar_nota.html', {'nota': nota})


@login_required
def lista_notas_entrada(request):
    """
    Lista de notas fiscais de entrada.
    """
    empresa = get_empresa_ativa(request)
    notas = NotaFiscalEntrada.objects.filter(
        is_active=True,
        loja__empresa=empresa,
    ).select_related(
        'loja', 'fornecedor'
    )
    
    # Filtros
    loja_filter = request.GET.get('loja')
    fornecedor_filter = request.GET.get('fornecedor')
    data_inicio = request.GET.get('data_inicio')
    data_fim = request.GET.get('data_fim')
    search = request.GET.get('search')
    
    if loja_filter:
        notas = notas.filter(loja_id=loja_filter, loja__empresa=empresa)
    if fornecedor_filter:
        notas = notas.filter(fornecedor_id=fornecedor_filter, fornecedor__empresa=empresa)
    if data_inicio:
        try:
            data_inicio_dt = datetime.strptime(data_inicio, '%Y-%m-%d')
            notas = notas.filter(data_entrada__gte=data_inicio_dt)
        except:
            pass
    if data_fim:
        try:
            data_fim_dt = datetime.strptime(data_fim, '%Y-%m-%d') + timedelta(days=1)
            notas = notas.filter(data_entrada__lt=data_fim_dt)
        except:
            pass
    if search:
        notas = notas.filter(
            Q(numero__icontains=search) |
            Q(chave_acesso__icontains=search) |
            Q(fornecedor__razao_social__icontains=search)
        )
    
    # Ordenação
    notas = notas.order_by('-data_entrada', '-numero')
    
    # Buscar dados para filtros
    from core.models import Loja
    from pessoas.models import Fornecedor
    
    lojas = Loja.objects.filter(empresa=empresa, is_active=True)
    fornecedores = Fornecedor.objects.filter(empresa=empresa, is_active=True)

    # Estatísticas
    total_valor = notas.aggregate(Sum('valor_total'))['valor_total__sum'] or 0
    total_notas = notas.count()

    context = {
        'notas': notas,
        'lojas': lojas,
        'fornecedores': fornecedores,
        'total_valor': total_valor,
        'total_notas': total_notas,
        'filtros': {
            'loja': loja_filter,
            'fornecedor': fornecedor_filter,
            'data_inicio': data_inicio,
            'data_fim': data_fim,
            'search': search,
        }
    }
    
    return render(request, 'fiscal/lista_notas_entrada.html', context)


@login_required
def detalhes_nota_entrada(request, nota_id):
    """
    Detalhes completos da nota fiscal de entrada.
    Exibe itens, botão "Dar entrada em estoque" e aviso de itens não vinculados.
    """
    empresa = get_empresa_ativa(request)
    nota = get_object_or_404(
        NotaFiscalEntrada.objects.select_related(
            'loja', 'fornecedor'
        ).prefetch_related('itens__produto', 'historico_entrada_estoque'),
        id=nota_id,
        loja__empresa=empresa,
        is_active=True
    )

    itens = nota.itens.filter(is_active=True).order_by('numero_item')
    itens_vinculados = itens.exclude(produto__isnull=True)
    itens_sem_vinculo = itens.filter(produto__isnull=True)
    itens_pendentes_entrada = itens_vinculados.exclude(status='ESTOQUE_ENTRADO')

    from estoque.models import LocalEstoque
    locais_estoque = LocalEstoque.objects.filter(
        loja=nota.loja,
        is_active=True
    ).order_by('nome')

    context = {
        'nota': nota,
        'itens': itens,
        'itens_sem_vinculo': itens_sem_vinculo,
        'itens_pendentes_entrada': itens_pendentes_entrada,
        'locais_estoque': locais_estoque,
        'pode_dar_entrada': itens_pendentes_entrada.exists() and locais_estoque.exists(),
    }
    return render(request, 'fiscal/detalhes_nota_entrada.html', context)


@login_required
@require_http_methods(['POST'])
def dar_entrada_estoque_nota_view(request, nota_id):
    """
    Processa a entrada em estoque para os itens vinculados da nota.
    """
    empresa = get_empresa_ativa(request)
    nota = get_object_or_404(
        NotaFiscalEntrada,
        id=nota_id,
        loja__empresa=empresa,
        is_active=True,
    )
    local_id = request.POST.get('local_estoque')
    if not local_id:
        messages.error(request, 'Selecione o local de estoque.')
        return redirect('fiscal:detalhes_nota_entrada', nota_id=nota.id)

    from estoque.models import LocalEstoque
    local = get_object_or_404(LocalEstoque, id=local_id, loja=nota.loja, is_active=True)

    from .services_entrada import dar_entrada_estoque_nota
    itens_processados, erros, motivo_parcial = dar_entrada_estoque_nota(
        nota, local, request.user
    )

    if itens_processados > 0:
        if erros:
            messages.warning(
                request,
                f'{itens_processados} item(ns) processado(s). Erros: {" | ".join(erros[:3])}'
                + (f' (+{len(erros)-3} mais)' if len(erros) > 3 else '')
            )
        else:
            messages.success(request, f'Entrada em estoque realizada: {itens_processados} item(ns) processado(s).')
    else:
        if erros:
            messages.error(request, 'Nenhum item processado. ' + (erros[0] if erros else ''))
        else:
            messages.warning(request, 'Nenhum item vinculado pendente de entrada.')

    return redirect('fiscal:detalhes_nota_entrada', nota_id=nota.id)


@login_required
@require_http_methods(['GET', 'POST'])
def criar_nota_entrada(request):
    """
    Digitação manual de Nota Fiscal de Entrada com itens (formset).
    Nota criada com status RASCUNHO se sem itens; CONFIRMADA se com itens.
    """
    from core.models import Loja
    from pessoas.models import Fornecedor

    empresa = get_empresa_ativa(request)
    loja_para_formset = None
    if request.method == 'POST':
        loja_id = request.POST.get('loja')
        if loja_id:
            try:
                loja_para_formset = Loja.objects.get(
                    id=loja_id,
                    empresa=empresa,
                    is_active=True,
                )
            except Loja.DoesNotExist:
                pass
    if loja_para_formset is None:
        loja_para_formset = Loja.objects.filter(empresa=empresa, is_active=True).first()

    formset = ItemNotaFiscalEntradaFormSet(loja=loja_para_formset)

    if request.method == 'POST':
        form = NotaFiscalEntradaForm(request.POST, empresa=empresa)
        formset = ItemNotaFiscalEntradaFormSet(request.POST, loja=loja_para_formset)

        if form.is_valid() and formset.is_valid():
            itens_com_dados = [f for f in formset if f.cleaned_data and f.cleaned_data.get('produto')]
            nota = form.save(commit=False)
            nota.created_by = request.user
            nota.updated_by = request.user
            nota.status = 'CONFIRMADA' if itens_com_dados else 'RASCUNHO'
            nota.save()

            for idx, item_form in enumerate(itens_com_dados, start=1):
                cd = item_form.cleaned_data
                if not cd.get('produto'):
                    continue
                produto = cd['produto']
                qtd = cd['quantidade']
                preco = cd['preco_unitario']
                valor_total = qtd * preco
                local = cd.get('local_estoque')
                if local and local.loja_id != nota.loja_id:
                    local = None
                ItemNotaFiscalEntrada.objects.create(
                    nota_fiscal=nota,
                    produto=produto,
                    numero_item=idx,
                    descricao=produto.descricao,
                    quantidade=qtd,
                    preco_unitario=preco,
                    valor_total=valor_total,
                    local_estoque=local,
                    status='VINCULADO',
                )

            messages.success(
                request,
                f'Nota Fiscal {nota.numero}/{nota.serie} cadastrada com sucesso.'
                + (f' {len(itens_com_dados)} item(ns) incluído(s).' if itens_com_dados else '')
            )
            return redirect('fiscal:detalhes_nota_entrada', nota_id=nota.id)
        else:
            if not form.is_valid():
                messages.error(request, 'Corrija os erros no formulário.')
            else:
                messages.error(request, 'Corrija os erros nos itens.')
    else:
        form = NotaFiscalEntradaForm(empresa=empresa)

    context = {
        'form': form,
        'formset': formset,
        'lojas': Loja.objects.filter(empresa=empresa, is_active=True),
        'fornecedores': Fornecedor.objects.filter(empresa=empresa, is_active=True),
    }
    return render(request, 'fiscal/nota_entrada_form.html', context)


@login_required
@require_http_methods(['GET', 'POST'])
def importar_nota_entrada_xml(request):
    """
    Importação de Nota Fiscal de Entrada a partir de arquivo XML.
    Passo 1: Upload do XML -> salva em tmp, chave na sessão.
    Passo 2: Usuário confirma loja/fornecedor e vincula produtos nos itens.
    """
    from pessoas.models import Fornecedor
    from core.models import Loja
    from fiscal.storage_nfe import salvar_xml_temporario, carregar_xml_temporario, deletar_xml_temporario
    from fiscal.produto_matching import encontrar_ou_sugerir_produto
    from datetime import datetime

    if request.method == 'POST':
        # Confirmação: criar nota e itens
        nfe_key = request.session.get('nfe_import_key')
        if nfe_key and request.POST.get('confirmar_import') == '1':
            try:
                xml_content = carregar_xml_temporario(nfe_key)
            except FileNotFoundError:
                messages.warning(request, 'Arquivo temporário expirado. Faça o upload novamente.')
                if 'nfe_import_key' in request.session:
                    del request.session['nfe_import_key']
                return redirect('fiscal:importar_nota_entrada_xml')

            try:
                dados = parse_nfe_xml(xml_content)
            except ValueError as e:
                messages.error(request, str(e))
                return redirect('fiscal:importar_nota_entrada_xml')

            loja_id = request.POST.get('loja')
            fornecedor_id = request.POST.get('fornecedor')
            data_entrada_str = request.POST.get('data_entrada')

            if not loja_id or not fornecedor_id:
                messages.error(request, 'Selecione a loja e o fornecedor.')
                return redirect('fiscal:importar_nota_entrada_confirmar')

            empresa = get_empresa_ativa(request)
            loja = get_object_or_404(Loja, id=loja_id, empresa=empresa, is_active=True)
            fornecedor = get_object_or_404(
                Fornecedor, id=fornecedor_id, empresa=empresa, is_active=True
            )

            data_emi = dados.get('data_emissao')
            if isinstance(data_emi, str):
                data_emi = datetime.strptime(data_emi, '%Y-%m-%d').date()
            data_entrada = datetime.strptime(data_entrada_str, '%Y-%m-%d').date() if data_entrada_str else data_emi

            nota = NotaFiscalEntrada.objects.create(
                loja=loja,
                fornecedor=fornecedor,
                numero=dados['numero'],
                serie=dados['serie'],
                chave_acesso=dados['chave_acesso'],
                valor_total=Decimal(str(dados['valor_total'])),
                data_emissao=data_emi,
                data_entrada=data_entrada,
                xml_arquivo=dados.get('xml_arquivo', ''),
                status='CONFIRMADA',
                created_by=request.user,
                updated_by=request.user,
            )

            # Criar itens
            itens = dados.get('itens', [])
            for item_data in itens:
                produto_id = request.POST.get(f"item_{item_data['numero_item']}_produto")
                produto = None
                produto_sugerido = None
                status = 'NAO_VINCULADO'
                if produto_id:
                    try:
                        from produtos.models import Produto
                        produto = get_object_or_404(
                            Produto,
                            id=produto_id,
                            is_active=True,
                            parametros_por_empresa__empresa=loja.empresa,
                            parametros_por_empresa__ativo_nessa_empresa=True,
                        )
                        status = 'VINCULADO'
                    except (ValueError, Http404):
                        pass

                ItemNotaFiscalEntrada.objects.create(
                    nota_fiscal=nota,
                    numero_item=item_data['numero_item'],
                    codigo_produto_fornecedor=item_data.get('codigo_produto_fornecedor', ''),
                    codigo_barras=item_data.get('codigo_barras', ''),
                    ncm=item_data.get('ncm', ''),
                    descricao=item_data.get('descricao', '')[:255],
                    quantidade=item_data['quantidade'],
                    unidade_comercial=item_data.get('unidade_comercial', 'UN')[:10],
                    preco_unitario=item_data['preco_unitario'],
                    valor_total=item_data['valor_total'],
                    produto=produto,
                    produto_sugerido=produto_sugerido,
                    status=status,
                    created_by=request.user,
                    updated_by=request.user,
                )

            AlertaNotaFiscal.objects.filter(chave_acesso=dados['chave_acesso']).update(
                status='IMPORTADA', nota_fiscal_entrada=nota, updated_by_id=request.user.id
            )
            deletar_xml_temporario(nfe_key)
            del request.session['nfe_import_key']
            messages.success(request, f'Nota Fiscal {nota.numero}/{nota.serie} importada com sucesso.')
            return redirect('fiscal:detalhes_nota_entrada', nota_id=nota.id)

        # Upload do XML
        arquivo = request.FILES.get('arquivo_xml')
        if not arquivo:
            messages.error(request, 'Selecione um arquivo XML.')
            return redirect('fiscal:importar_nota_entrada_xml')

        if not arquivo.name.lower().endswith(('.xml', '.nfe')):
            messages.error(request, 'O arquivo deve ser um XML de NF-e (.xml ou .nfe).')
            return redirect('fiscal:importar_nota_entrada_xml')

        try:
            xml_content = arquivo.read().decode('utf-8', errors='replace')
        except Exception as e:
            messages.error(request, f'Erro ao ler arquivo: {e}')
            return redirect('fiscal:importar_nota_entrada_xml')

        try:
            dados = parse_nfe_xml(xml_content)
        except ValueError as e:
            messages.error(request, str(e))
            return redirect('fiscal:importar_nota_entrada_xml')

        if NotaFiscalEntrada.objects.filter(chave_acesso=dados['chave_acesso'], is_active=True).exists():
            messages.warning(request, 'Nota com esta chave já está cadastrada.')
            return redirect('fiscal:lista_notas_entrada')

        key = salvar_xml_temporario(xml_content)
        request.session['nfe_import_key'] = key
        return redirect('fiscal:importar_nota_entrada_confirmar')

    return render(request, 'fiscal/importar_nota_xml.html')


@login_required
@require_http_methods(['GET', 'POST'])
def importar_nota_entrada_confirmar(request):
    """
    Confirmação da importação - usuário seleciona loja, fornecedor e vincula produtos nos itens.
    Dados carregados do arquivo temporário (chave na sessão).
    """
    from pessoas.models import Fornecedor
    from core.models import Loja
    from datetime import datetime
    from fiscal.storage_nfe import carregar_xml_temporario, deletar_xml_temporario
    from fiscal.produto_matching import encontrar_ou_sugerir_produto

    nfe_key = request.session.get('nfe_import_key')
    if not nfe_key:
        messages.warning(request, 'Sessão expirada. Faça o upload do XML novamente.')
        return redirect('fiscal:importar_nota_entrada_xml')

    if request.method == 'GET' and request.GET.get('cancelar'):
        deletar_xml_temporario(nfe_key)
        if 'nfe_import_key' in request.session:
            del request.session['nfe_import_key']
        return redirect('fiscal:importar_nota_entrada_xml')

    try:
        xml_content = carregar_xml_temporario(nfe_key)
    except FileNotFoundError:
        messages.warning(request, 'Arquivo temporário expirado. Faça o upload novamente.')
        if 'nfe_import_key' in request.session:
            del request.session['nfe_import_key']
        return redirect('fiscal:importar_nota_entrada_xml')

    try:
        dados = parse_nfe_xml(xml_content)
    except ValueError as e:
        messages.error(request, str(e))
        return redirect('fiscal:importar_nota_entrada_xml')

    # Matching de produtos para cada item
    empresa_sessao = get_empresa_ativa(request)
    primeira_loja = (
        Loja.objects.filter(empresa=empresa_sessao, is_active=True)
        .select_related('empresa')
        .first()
    )
    empresa = empresa_sessao
    fornecedor_match = None  # Será definido quando usuário selecionar

    itens = dados.get('itens', [])
    for item in itens:
        produto, produto_sugerido, status = encontrar_ou_sugerir_produto(
            item, fornecedor_match, empresa
        )
        item['produto'] = produto
        item['produto_sugerido'] = produto_sugerido
        item['status_matching'] = status

    # Restaurar data para exibição
    data_emi = dados.get('data_emissao')
    if isinstance(data_emi, str):
        try:
            dados['data_emissao'] = datetime.strptime(data_emi, '%Y-%m-%d').date()
        except (ValueError, TypeError):
            dados['data_emissao'] = datetime.now().date()
    elif data_emi is None:
        dados['data_emissao'] = datetime.now().date()

    from produtos.models import Produto
    produtos = (
        Produto.objects.filter(
            is_active=True,
            parametros_por_empresa__empresa=empresa_sessao,
            parametros_por_empresa__ativo_nessa_empresa=True,
        )
        .distinct()
        .order_by('descricao')
    )

    context = {
        'dados': dados,
        'itens': itens,
        'lojas': Loja.objects.filter(empresa=empresa_sessao, is_active=True),
        'fornecedores': Fornecedor.objects.filter(empresa=empresa_sessao, is_active=True),
        'produtos': produtos,
    }
    return render(request, 'fiscal/importar_nota_xml_confirmar.html', context)


@login_required
def lista_alertas_sefaz(request):
    """
    Lista de alertas de notas fiscais da SEFAZ-BA.
    """
    empresa = get_empresa_ativa(request)
    alertas = AlertaNotaFiscal.objects.filter(
        is_active=True,
        loja__empresa=empresa,
    ).select_related('loja', 'nota_fiscal_entrada').order_by('-data_consulta_sefaz')

    status_filter = request.GET.get('status')
    if status_filter:
        alertas = alertas.filter(status=status_filter)

    context = {
        'alertas': alertas,
        'total_pendentes': alertas.filter(status='PENDENTE').count(),
    }
    return render(request, 'fiscal/lista_alertas_sefaz.html', context)


@login_required
def testar_status_sefaz(request, loja_id):
    """
    View de diagnostico para testar conexao com SEFAZ por loja.
    """
    from .nfe_status import consultar_status_servico_nfe

    if not request.user.is_staff:
        raise PermissionDenied

    empresa = get_empresa_ativa(request)
    loja = get_object_or_404(Loja, pk=loja_id, empresa=empresa, is_active=True)

    try:
        config = loja.configuracao_fiscal
    except ConfiguracaoFiscalLoja.DoesNotExist:
        messages.error(request, f"Loja {loja.nome} nao possui configuracao fiscal.")
        return redirect('fiscal:lista_config_fiscal')

    resultado = consultar_status_servico_nfe(config)
    if resultado.get('ok'):
        messages.success(
            request,
            "SEFAZ-BA respondeu: "
            f"{resultado.get('xMotivo', '')} "
            f"(cStat={resultado.get('cStat', '')}) - "
            f"Ambiente: {resultado.get('ambiente', '')}"
        )
    else:
        messages.error(
            request,
            "Falha na conexao SEFAZ-BA: "
            f"{resultado.get('erro') or resultado.get('xMotivo', '')} - "
            f"Ambiente: {resultado.get('ambiente', '')}"
        )
    return redirect(request.META.get('HTTP_REFERER', '/'))


@login_required
def imprimir_nfe_pdf(request, nota_id):
    """
    Gera PDF da NF-e no layout SEFAZ-BA.
    
    Requer weasyprint instalado: pip install weasyprint
    """
    if not WEASYPRINT_AVAILABLE:
        return HttpResponse(
            '<h1>Erro: WeasyPrint não instalado</h1>'
            '<p>Para gerar PDFs, instale o weasyprint:</p>'
            '<pre>pip install weasyprint</pre>',
            status=500
        )
    
    empresa = get_empresa_ativa(request)
    nota = get_object_or_404(
        NotaFiscalSaida,
        id=nota_id,
        loja__empresa=empresa,
        is_active=True,
    )
    
    # Buscar dados relacionados
    pedido = nota.pedido_venda
    itens = []
    if pedido:
        itens = list(
            pedido.itens.filter(is_active=True).select_related('produto')
        )

    loja_empresa = nota.loja.empresa

    from produtos.models import ProdutoParametrosEmpresa

    params_map = {}
    if itens:
        produto_ids = [item.produto_id for item in itens]
        params_qs = ProdutoParametrosEmpresa.objects.filter(
            empresa=loja_empresa,
            produto_id__in=produto_ids,
        )
        params_map = {p.produto_id: p for p in params_qs}

    itens_com_params = []
    for item in itens:
        params = params_map.get(item.produto_id)
        itens_com_params.append({
            'item': item,
            'cfop': params.cfop_venda_dentro_uf if params else None,
            'cst': params.csosn_cst if params else None,
        })

    # Buscar configuração fiscal da loja
    config_fiscal = None
    try:
        config_fiscal = nota.loja.configuracao_fiscal
    except ConfiguracaoFiscalLoja.DoesNotExist:
        pass

    cnpj_emitente_raw = ''
    if config_fiscal and config_fiscal.cnpj:
        cnpj_emitente_raw = config_fiscal.cnpj
    elif loja_empresa.cnpj:
        cnpj_emitente_raw = loja_empresa.cnpj
    cnpj_emitente_formatado = _formatar_cnpj(cnpj_emitente_raw)

    cliente = nota.cliente
    cpf_cnpj_dest_formatado = _formatar_cpf_ou_cnpj(
        cliente.cpf_cnpj if cliente else ''
    )

    qrcode_b64 = _gerar_qrcode_nfe_base64(nota.chave_acesso or '')

    # Calcular impostos conforme normas SEFAZ-BA
    # IMPORTANTE: Para Simples Nacional, os impostos não são calculados separadamente
    # Usar get_impostos() que já considera snapshot se autorizada
    impostos = nota.get_impostos()

    # Preparar contexto
    context = {
        'nota': nota,
        'loja': nota.loja,
        'empresa': loja_empresa,
        'cliente': cliente,
        'pedido': pedido,
        'itens': itens,
        'itens_com_params': itens_com_params,
        'config_fiscal': config_fiscal,
        'impostos': impostos,
        'cnpj_emitente_formatado': cnpj_emitente_formatado,
        'cpf_cnpj_dest_formatado': cpf_cnpj_dest_formatado,
        'qrcode_b64': qrcode_b64,
    }
    
    # Renderizar template HTML
    html_string = render_to_string('fiscal/nfe_pdf.html', context)
    
    # Gerar PDF
    html = HTML(string=html_string)
    pdf = html.write_pdf()
    
    # Retornar PDF como resposta
    response = HttpResponse(pdf, content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename="NF-e_{nota.numero}_{nota.serie}.pdf"'
    
    return response


# ---------------------------------------------------------------------------
# NFC-e (modelo 65)
# ---------------------------------------------------------------------------


def _nfce_queryset(request):
    empresa = get_empresa_ativa(request)
    return NotaFiscalConsumidor.objects.filter(
        is_active=True,
        loja__empresa=empresa,
    ).select_related('loja', 'pedido_venda')


@login_required
def lista_nfce(request):
    notas = _nfce_queryset(request).order_by('-created_at')
    status_filter = request.GET.get('status')
    if status_filter:
        notas = notas.filter(status=status_filter)
    return render(request, 'fiscal/lista_nfce.html', {
        'notas': notas,
        'status_filter': status_filter,
        'status_choices': NotaFiscalConsumidor.STATUS_CHOICES,
    })


@login_required
@require_http_methods(['GET', 'POST'])
def criar_nfce(request):
    empresa = get_empresa_ativa(request)
    if request.method == 'POST':
        form = NotaFiscalConsumidorForm(request.POST, empresa=empresa)
        if form.is_valid():
            nfce = form.save(commit=False)
            nfce.created_by = request.user
            try:
                from .numeracao import reservar_numero_nfce
                numero, serie = reservar_numero_nfce(nfce.loja)
            except ConfiguracaoFiscalLoja.DoesNotExist:
                numero, serie = 1, '001'
            nfce.numero = numero
            nfce.serie = serie
            try:
                config = nfce.loja.configuracao_fiscal
                nfce.ambiente = config.ambiente
            except ConfiguracaoFiscalLoja.DoesNotExist:
                pass
            nfce.save()
            messages.success(request, f'NFC-e {nfce.numero}/{nfce.serie} criada em rascunho.')
            return redirect('fiscal:detalhes_nfce', nota_id=nfce.id)
    else:
        form = NotaFiscalConsumidorForm(empresa=empresa)
    return render(request, 'fiscal/form_nfce.html', {'form': form, 'titulo': 'Nova NFC-e'})


@login_required
def detalhes_nfce(request, nota_id):
    nfce = get_object_or_404(_nfce_queryset(request), pk=nota_id)
    return render(request, 'fiscal/detalhes_nfce.html', {'nota': nfce})


@login_required
@require_http_methods(['POST'])
def autorizar_nfce_view(request, nota_id):
    if not request.user.is_staff:
        raise PermissionDenied

    nfce = get_object_or_404(_nfce_queryset(request), pk=nota_id)
    from .nfce_autorizacao import autorizar_nfce

    try:
        resultado = autorizar_nfce(nfce)
        if resultado.get('sucesso'):
            messages.success(
                request,
                f'NFC-e {nfce.numero}/{nfce.serie} autorizada. Protocolo: {nfce.protocolo or "—"}',
            )
        else:
            messages.error(
                request,
                f'NFC-e rejeitada (cStat {resultado.get("cStat")}): {resultado.get("xMotivo")}',
            )
    except Exception as exc:
        messages.error(request, f'Erro ao autorizar NFC-e: {exc}')
        logger.exception('Erro ao autorizar NFC-e %s', nota_id)

    return redirect('fiscal:detalhes_nfce', nota_id=nota_id)


@login_required
@require_http_methods(['GET', 'POST'])
def cancelar_nfce_view(request, nota_id):
    if not request.user.is_staff:
        raise PermissionDenied

    nfce = get_object_or_404(_nfce_queryset(request), pk=nota_id)
    if request.method == 'POST':
        justificativa = request.POST.get('justificativa', '').strip()
        from .nfce_autorizacao import cancelar_nfce
        try:
            cancelar_nfce(nfce, justificativa)
            messages.success(request, 'NFC-e cancelada.')
            return redirect('fiscal:detalhes_nfce', nota_id=nota_id)
        except ValueError as exc:
            messages.error(request, str(exc))
    return render(request, 'fiscal/cancelar_nfce.html', {'nota': nfce})


@login_required
def imprimir_danfe_nfce(request, nota_id):
    nfce = get_object_or_404(_nfce_queryset(request), pk=nota_id)
    if not WEASYPRINT_AVAILABLE:
        return HttpResponse(
            '<h1>WeasyPrint não instalado</h1><p>pip install weasyprint</p>',
            status=500,
        )
    context = {
        'nota': nfce,
        'loja': nfce.loja,
        'itens': nfce.itens.filter(is_active=True),
        'qrcode_b64': _gerar_qrcode_nfe_base64(nfce.chave_acesso or ''),
    }
    html_string = render_to_string('fiscal/danfe_nfce.html', context)
    pdf = HTML(string=html_string).write_pdf()
    response = HttpResponse(pdf, content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename="NFCe_{nfce.numero}_{nfce.serie}.pdf"'
    return response


# ---------------------------------------------------------------------------
# NFS-e Nacional
# ---------------------------------------------------------------------------


def _nfse_queryset(request):
    empresa = get_empresa_ativa(request)
    return NotaFiscalServico.objects.filter(
        is_active=True,
        loja__empresa=empresa,
    ).select_related('loja', 'pedido_venda')


@login_required
def lista_nfse(request):
    notas = _nfse_queryset(request).order_by('-created_at')
    status_filter = request.GET.get('status')
    if status_filter:
        notas = notas.filter(status=status_filter)
    return render(request, 'fiscal/lista_nfse.html', {
        'notas': notas,
        'status_filter': status_filter,
        'status_choices': NotaFiscalServico.STATUS_CHOICES,
    })


@login_required
@require_http_methods(['GET', 'POST'])
def criar_nfse(request):
    empresa = get_empresa_ativa(request)
    if request.method == 'POST':
        form = NotaFiscalServicoForm(request.POST, empresa=empresa)
        if form.is_valid():
            nfse = form.save(commit=False)
            nfse.created_by = request.user
            try:
                from .numeracao import reservar_numero_rps
                numero_rps, serie_rps = reservar_numero_rps(nfse.loja)
            except ConfiguracaoFiscalLoja.DoesNotExist:
                numero_rps, serie_rps = 1, 'RPS'
            nfse.numero_rps = numero_rps
            nfse.serie_rps = serie_rps
            if not nfse.municipio_prestacao:
                try:
                    loja = nfse.loja
                    nfse.municipio_prestacao = (
                        loja.codigo_ibge_municipio
                        or loja.empresa.codigo_ibge_municipio
                        or ''
                    )
                except Exception:
                    pass
            nfse.save()
            from .nfse_nacional import calcular_valores_nfse
            calcular_valores_nfse(nfse)
            messages.success(request, f'NFS-e RPS {nfse.numero_rps} criada em rascunho.')
            return redirect('fiscal:detalhes_nfse', nota_id=nfse.id)
    else:
        form = NotaFiscalServicoForm(empresa=empresa)
    return render(request, 'fiscal/form_nfse.html', {'form': form, 'titulo': 'Nova NFS-e'})


@login_required
def detalhes_nfse(request, nota_id):
    nfse = get_object_or_404(_nfse_queryset(request), pk=nota_id)
    return render(request, 'fiscal/detalhes_nfse.html', {'nota': nfse})


@login_required
@require_http_methods(['POST'])
def emitir_nfse_view(request, nota_id):
    if not request.user.is_staff:
        raise PermissionDenied

    nfse = get_object_or_404(_nfse_queryset(request), pk=nota_id)
    try:
        config = nfse.loja.configuracao_fiscal
    except ConfiguracaoFiscalLoja.DoesNotExist:
        messages.error(request, 'Loja sem configuração fiscal.')
        return redirect('fiscal:detalhes_nfse', nota_id=nota_id)

    from .nfse_nacional import emitir_nfse
    try:
        resultado = emitir_nfse(nfse, config)
        if resultado.get('sucesso'):
            messages.success(request, f'NFS-e emitida. Número: {resultado.get("numero")}')
        else:
            messages.error(request, f'NFS-e rejeitada: {resultado.get("erro", "Erro desconhecido")}')
    except Exception as exc:
        messages.error(request, f'Erro ao emitir NFS-e: {exc}')
        logger.exception('Erro ao emitir NFS-e %s', nota_id)

    return redirect('fiscal:detalhes_nfse', nota_id=nota_id)


@login_required
@require_http_methods(['GET', 'POST'])
def cancelar_nfse_view(request, nota_id):
    if not request.user.is_staff:
        raise PermissionDenied

    nfse = get_object_or_404(_nfse_queryset(request), pk=nota_id)
    if request.method == 'POST':
        motivo = request.POST.get('motivo', '').strip()
        from .nfse_nacional import cancelar_nfse
        try:
            cancelar_nfse(nfse, motivo)
            messages.success(request, 'NFS-e cancelada.')
            return redirect('fiscal:detalhes_nfse', nota_id=nota_id)
        except ValueError as exc:
            messages.error(request, str(exc))
    return render(request, 'fiscal/cancelar_nfse.html', {'nota': nfse})


@login_required
def imprimir_nfse_pdf(request, nota_id):
    nfse = get_object_or_404(_nfse_queryset(request), pk=nota_id)
    if not WEASYPRINT_AVAILABLE:
        return HttpResponse(
            '<h1>WeasyPrint não instalado</h1><p>pip install weasyprint</p>',
            status=500,
        )
    context = {'nota': nfse, 'loja': nfse.loja}
    html_string = render_to_string('fiscal/nfse_pdf.html', context)
    pdf = HTML(string=html_string).write_pdf()
    response = HttpResponse(pdf, content_type='application/pdf')
    num = nfse.numero or nfse.numero_rps
    response['Content-Disposition'] = f'inline; filename="NFSe_{num}.pdf"'
    return response

