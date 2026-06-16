"""
Views do app produtos.
"""
from django.http import JsonResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q
from django.views.decorators.http import require_http_methods
from rest_framework import viewsets

from pessoas.models import Fornecedor

from django.db.models import OuterRef, Subquery

from .forms import CodigoBarrasAlternativoForm, ProdutoForm, ProdutoParametrosEmpresaForm
from .models import CategoriaProduto, CodigoBarrasAlternativo, Produto, ProdutoParametrosEmpresa
from .serializers import CategoriaProdutoSerializer, ProdutoSerializer
from core.tenant import get_empresa_ativa


class CategoriaProdutoViewSet(viewsets.ModelViewSet):
    queryset = CategoriaProduto.objects.filter(is_active=True)
    serializer_class = CategoriaProdutoSerializer


class ProdutoViewSet(viewsets.ModelViewSet):
    serializer_class = ProdutoSerializer

    def get_queryset(self):
        empresa = get_empresa_ativa(self.request)
        return (
            Produto.objects.filter(
                is_active=True,
                parametros_por_empresa__empresa=empresa,
                parametros_por_empresa__ativo_nessa_empresa=True,
            )
            .distinct()
        )


@login_required
def lista_produtos(request):
    """
    Lista de produtos com filtros.
    """
    empresa = get_empresa_ativa(request)
    produtos = (
        Produto.objects.filter(
            is_active=True,
            parametros_por_empresa__empresa=empresa,
            parametros_por_empresa__ativo_nessa_empresa=True,
        )
        .select_related('categoria')
        .distinct()
    )
    
    # Filtros
    categoria_filter = request.GET.get('categoria')
    classe_risco_filter = request.GET.get('classe_risco')
    empresa_filter = request.GET.get('empresa')
    restricao_exercito = request.GET.get('restricao_exercito')
    search = request.GET.get('search')
    
    if categoria_filter:
        produtos = produtos.filter(categoria_id=categoria_filter)
    if classe_risco_filter:
        produtos = produtos.filter(classe_risco=classe_risco_filter)
    if empresa_filter and str(empresa_filter) == str(empresa.id):
        sub = ProdutoParametrosEmpresa.objects.filter(
            produto_id=OuterRef('pk'),
            empresa_id=empresa_filter,
            ativo_nessa_empresa=True,
        )
        produtos = produtos.annotate(preco_lista=Subquery(sub.values('preco_venda')[:1]))
    if restricao_exercito == 'sim':
        produtos = produtos.filter(possui_restricao_exercito=True)
    elif restricao_exercito == 'nao':
        produtos = produtos.filter(possui_restricao_exercito=False)
    if search:
        # Inclui códigos alternativos na busca da listagem
        ids_alt = CodigoBarrasAlternativo.objects.filter(
            codigo_barras__icontains=search,
            produto__in=produtos,
            produto__is_active=True,
            is_active=True,
        ).values_list('produto_id', flat=True)
        produtos = produtos.filter(
            Q(codigo_interno__icontains=search)
            | Q(codigo_barras__icontains=search)
            | Q(descricao__icontains=search)
            | Q(ncm__icontains=search)
            | Q(id__in=ids_alt)
        )
    
    # Ordenação
    produtos = produtos.order_by('codigo_interno', 'descricao')
    
    # Buscar dados para filtros
    from core.models import Empresa
    empresas = Empresa.objects.filter(pk=empresa.pk)
    categorias = CategoriaProduto.objects.filter(is_active=True)
    
    context = {
        'produtos': produtos,
        'empresas': empresas,
        'categorias': categorias,
        'classe_risco_choices': Produto.CLASSE_RISCO_CHOICES,
        'filtros': {
            'categoria': categoria_filter,
            'classe_risco': classe_risco_filter,
            'empresa': empresa_filter,
            'restricao_exercito': restricao_exercito,
            'search': search,
        }
    }
    
    return render(request, 'produtos/lista_produtos.html', context)


@login_required
def detalhes_produto(request, produto_id):
    """
    Detalhes completos do produto.
    """
    empresa = get_empresa_ativa(request)
    produto = get_object_or_404(
        Produto.objects.select_related('categoria'),
        id=produto_id,
        is_active=True,
        parametros_por_empresa__empresa=empresa,
        parametros_por_empresa__ativo_nessa_empresa=True,
    )

    # Buscar estoque atual
    from estoque.models import EstoqueAtual
    estoques = EstoqueAtual.objects.filter(
        produto=produto,
        local_estoque__loja__empresa=empresa,
        is_active=True,
    ).select_related('local_estoque', 'local_estoque__loja')

    parametros_empresa = produto.parametros_por_empresa.select_related('empresa').filter(
        empresa=empresa,
        is_active=True,
    ).order_by('empresa__nome_fantasia')

    context = {
        'produto': produto,
        'estoques': estoques,
        'parametros_empresa': parametros_empresa,
    }
    
    return render(request, 'produtos/detalhes_produto.html', context)


@login_required
def criar_produto(request):
    """
    Cria um novo produto (catálogo global) e parâmetros na empresa selecionada.
    """
    from decimal import Decimal

    from core.models import Empresa
    from django.db import transaction

    empresa = get_empresa_ativa(request)
    empresas = Empresa.objects.filter(pk=empresa.pk)
    categorias = CategoriaProduto.objects.filter(is_active=True)

    if request.method == 'POST':
        try:
            empresa_id = empresa.pk

            with transaction.atomic():
                produto = Produto.objects.create(
                    categoria_id=request.POST.get('categoria'),
                    codigo_barras=(request.POST.get('codigo_barras') or '').strip() or None,
                    descricao=request.POST.get('descricao'),
                    classe_risco='OUTRA',
                    numero_lote=request.POST.get('numero_lote') or None,
                    validade=request.POST.get('validade') or None,
                    condicoes_armazenamento=request.POST.get('condicoes_armazenamento') or None,
                    ncm=request.POST.get('ncm'),
                    cest=request.POST.get('cest') or None,
                    unidade_comercial=request.POST.get('unidade_comercial', 'UN'),
                    origem=request.POST.get('origem', '0'),
                    observacoes=request.POST.get('observacoes') or None,
                    created_by=request.user,
                )
                pv_raw = request.POST.get('preco_venda_sugerido')
                if not pv_raw:
                    raise ValueError('Preço de venda é obrigatório.')
                ProdutoParametrosEmpresa.objects.create(
                    empresa_id=empresa_id,
                    produto=produto,
                    preco_venda=Decimal(str(pv_raw.replace(',', '.'))),
                    cfop_venda_dentro_uf=request.POST.get('cfop_venda_dentro_uf'),
                    cfop_venda_fora_uf=request.POST.get('cfop_venda_fora_uf') or None,
                    csosn_cst=request.POST.get('csosn_cst'),
                    aliquota_icms=Decimal(str(request.POST.get('aliquota_icms', '18'))),
                    icms_st_cst=request.POST.get('icms_st_cst') or None,
                    aliquota_icms_st=Decimal(str(request.POST.get('aliquota_icms_st', '0') or '0')),
                    pis_cst=request.POST.get('pis_cst', '01'),
                    aliquota_pis=Decimal(str(request.POST.get('aliquota_pis', '1.65'))),
                    cofins_cst=request.POST.get('cofins_cst', '01'),
                    aliquota_cofins=Decimal(str(request.POST.get('aliquota_cofins', '7.60'))),
                    ipi_venda_cst=request.POST.get('ipi_venda_cst', '52'),
                    aliquota_ipi_venda=Decimal(str(request.POST.get('aliquota_ipi_venda', '0'))),
                    ipi_compra_cst=request.POST.get('ipi_compra_cst', '02'),
                    aliquota_ipi_compra=Decimal(str(request.POST.get('aliquota_ipi_compra', '0') or '0')),
                    cclass_trib=request.POST.get('cclass_trib') or None,
                    cst_ibs=request.POST.get('cst_ibs') or None,
                    cst_cbs=request.POST.get('cst_cbs') or None,
                    aliquota_ibs=Decimal(str(request.POST.get('aliquota_ibs', '0.10'))),
                    aliquota_cbs=Decimal(str(request.POST.get('aliquota_cbs', '0.90'))),
                    ativo_nessa_empresa=True,
                    created_by=request.user,
                )

            messages.success(request, f'Produto "{produto.descricao}" criado com sucesso!')
            return redirect('produtos:detalhes_produto', produto_id=produto.id)

        except Exception as e:
            context = {
                'empresas': empresas,
                'categorias': categorias,
                'erro': str(e),
                'form_data': request.POST,
            }
            return render(request, 'produtos/criar_produto.html', context)

    context = {
        'empresas': empresas,
        'categorias': categorias,
    }

    return render(request, 'produtos/criar_produto.html', context)


@login_required
@require_http_methods(['GET', 'POST'])
def produto_editar(request, produto_id):
    """Edição de produto (global + parâmetros da empresa selecionada)."""
    from core.models import Empresa

    empresa = get_empresa_ativa(request)
    produto = get_object_or_404(
        Produto.objects.select_related('categoria'),
        pk=produto_id,
        is_active=True,
        parametros_por_empresa__empresa=empresa,
        parametros_por_empresa__ativo_nessa_empresa=True,
    )
    empresa_ids = [empresa.pk]
    empresas_com_params = Empresa.objects.filter(pk=empresa.pk)

    empresa_param_id = request.GET.get('empresa_id') or request.POST.get('param_empresa_id')
    param_empresa = empresa
    if empresa_param_id and str(empresa_param_id) == str(empresa.pk):
        param_empresa = empresa

    params_instance = None
    if param_empresa:
        params_instance = produto.parametros_por_empresa.filter(empresa=param_empresa).first()

    if request.method == 'POST':
        form = ProdutoForm(request.POST, instance=produto)
        params_form = None
        if param_empresa:
            params_form = ProdutoParametrosEmpresaForm(
                request.POST,
                instance=params_instance,
                prefix='params',
            )
            if params_instance is None:
                params_form.instance.produto = produto
                params_form.instance.empresa = param_empresa
        params_ok = params_form.is_valid() if params_form else True
        if form.is_valid() and params_ok:
            p = form.save(commit=False)
            p.updated_by = request.user
            p.save()
            if params_form:
                pp = params_form.save(commit=False)
                pp.produto = produto
                if not pp.empresa_id:
                    pp.empresa = param_empresa
                pp.updated_by = request.user
                pp.save()
            messages.success(request, f'Produto "{p.descricao}" atualizado com sucesso.')
            return redirect('produtos:detalhes_produto', produto_id=p.id)
    else:
        form = ProdutoForm(instance=produto)
        params_form = None
        if param_empresa:
            params_form = ProdutoParametrosEmpresaForm(
                instance=params_instance,
                prefix='params',
            )
            if params_instance is None:
                params_form.initial['empresa'] = param_empresa.pk

    return render(request, 'produtos/produto_editar.html', {
        'form': form,
        'params_form': params_form,
        'produto': produto,
        'empresas_com_params': empresas_com_params,
        'param_empresa': param_empresa,
    })


@login_required
@require_http_methods(['GET'])
def produto_codigos_alternativos(request, produto_id):
    """Página de códigos alternativos do produto."""
    empresa = get_empresa_ativa(request)
    produto = get_object_or_404(
        Produto.objects.select_related('categoria'),
        pk=produto_id,
        is_active=True,
        parametros_por_empresa__empresa=empresa,
        parametros_por_empresa__ativo_nessa_empresa=True,
    )
    codigos = produto.codigos_alternativos.filter(is_active=True).select_related('fornecedor').order_by('codigo_barras')
    empresa_ids = [empresa.pk]
    fornecedores = Fornecedor.objects.filter(
        empresa_id__in=empresa_ids, is_active=True
    ).order_by('razao_social')
    form_add = CodigoBarrasAlternativoForm(empresa_ids=empresa_ids or None)
    return render(request, 'produtos/produto_codigos_alternativos.html', {
        'produto': produto,
        'codigos': codigos,
        'fornecedores': fornecedores,
        'form_add': form_add,
    })


@login_required
@require_http_methods(['POST'])
def codigo_alternativo_criar(request, produto_id):
    """Criar código alternativo via AJAX. Sempre retorna JSON."""
    empresa = get_empresa_ativa(request)
    produto = get_object_or_404(
        Produto,
        pk=produto_id,
        is_active=True,
        parametros_por_empresa__empresa=empresa,
        parametros_por_empresa__ativo_nessa_empresa=True,
    )
    empresa_ids = [empresa.pk]
    fornecedor_id = request.POST.get('fornecedor_id')
    fornecedor = None
    if fornecedor_id:
        try:
            fornecedor = Fornecedor.objects.get(
                pk=int(fornecedor_id),
                empresa_id__in=empresa_ids,
                is_active=True,
            )
        except (Fornecedor.DoesNotExist, ValueError, TypeError):
            return JsonResponse({
                'success': False,
                'message': 'Fornecedor inválido ou não vinculado às empresas deste produto.',
            }, status=400)
    form = CodigoBarrasAlternativoForm(request.POST, empresa_ids=empresa_ids or None)
    form.instance.produto = produto
    if form.is_valid():
        try:
            codigo = form.save(commit=False)
            codigo.fornecedor = fornecedor
            codigo.created_by = request.user
            codigo.full_clean()
            codigo.save()
            return JsonResponse({
                'success': True,
                'message': 'Código alternativo adicionado com sucesso!',
                'codigo': {
                    'id': codigo.id,
                    'codigo_barras': codigo.codigo_barras,
                    'descricao': codigo.descricao or '',
                    'multiplicador': f'{codigo.multiplicador:.3f}',
                    'fornecedor_id': codigo.fornecedor_id,
                    'fornecedor_nome': codigo.fornecedor.razao_social if codigo.fornecedor else None,
                },
            })
        except Exception as e:
            return JsonResponse({'success': False, 'message': f'Erro ao salvar: {str(e)}'}, status=400)
    errors = []
    for _f, errs in form.errors.items():
        for e in errs:
            errors.append(str(e))
    return JsonResponse({'success': False, 'message': ' | '.join(errors)}, status=400)


@login_required
@require_http_methods(['POST'])
def codigo_alternativo_editar(request, codigo_id):
    """Editar código alternativo via AJAX. Sempre retorna JSON."""
    empresa = get_empresa_ativa(request)
    codigo = get_object_or_404(
        CodigoBarrasAlternativo,
        pk=codigo_id,
        is_active=True,
        produto__parametros_por_empresa__empresa=empresa,
        produto__parametros_por_empresa__ativo_nessa_empresa=True,
    )
    fornecedor_id = request.POST.get('fornecedor_id')
    fornecedor = None
    empresa_ids = [empresa.pk]
    if fornecedor_id:
        try:
            fornecedor = Fornecedor.objects.get(
                pk=int(fornecedor_id),
                empresa_id__in=empresa_ids,
                is_active=True,
            )
        except (Fornecedor.DoesNotExist, ValueError, TypeError):
            return JsonResponse({
                'success': False,
                'message': 'Fornecedor inválido ou não vinculado às empresas deste produto.',
            }, status=400)
    form = CodigoBarrasAlternativoForm(
        request.POST, instance=codigo, empresa_ids=empresa_ids or None
    )
    if form.is_valid():
        try:
            c = form.save(commit=False)
            c.fornecedor = fornecedor
            c.updated_by = request.user
            c.full_clean()
            c.save()
            return JsonResponse({
                'success': True,
                'message': 'Código alternativo atualizado com sucesso!',
                'codigo': {
                    'id': c.id,
                    'codigo_barras': c.codigo_barras,
                    'descricao': c.descricao or '',
                    'multiplicador': f'{c.multiplicador:.3f}',
                    'fornecedor_id': c.fornecedor_id,
                    'fornecedor_nome': c.fornecedor.razao_social if c.fornecedor else None,
                },
            })
        except Exception as e:
            return JsonResponse({'success': False, 'message': f'Erro ao salvar: {str(e)}'}, status=400)
    errors = []
    for _f, errs in form.errors.items():
        for e in errs:
            errors.append(str(e))
    return JsonResponse({'success': False, 'message': ' | '.join(errors)}, status=400)


@login_required
@require_http_methods(['POST'])
def codigo_alternativo_inativar(request, codigo_id):
    """Inativar código alternativo via AJAX. Sempre retorna JSON."""
    empresa = get_empresa_ativa(request)
    codigo = get_object_or_404(
        CodigoBarrasAlternativo,
        pk=codigo_id,
        is_active=True,
        produto__parametros_por_empresa__empresa=empresa,
        produto__parametros_por_empresa__ativo_nessa_empresa=True,
    )
    codigo.is_active = False
    codigo.updated_by = request.user
    codigo.save()
    return JsonResponse({
        'success': True,
        'message': 'Código alternativo removido com sucesso.',
    })


@login_required
@require_http_methods(['GET', 'POST'])
def produto_inativar(request, produto_id):
    """Confirmação e inativação de produto (soft delete)."""
    empresa = get_empresa_ativa(request)
    produto = get_object_or_404(
        Produto.objects.select_related('categoria'),
        pk=produto_id,
        is_active=True,
        parametros_por_empresa__empresa=empresa,
        parametros_por_empresa__ativo_nessa_empresa=True,
    )
    if request.method == 'POST':
        produto.is_active = False
        produto.updated_by = request.user
        produto.save()
        produto.codigos_alternativos.filter(is_active=True).update(is_active=False)
        messages.success(request, f'Produto "{produto.descricao}" foi inativado.')
        return redirect('produtos:lista_produtos')
    codigos_ativos = produto.codigos_alternativos.filter(is_active=True)
    preco_ref = (
        produto.parametros_por_empresa.filter(empresa=empresa)
        .order_by('pk')
        .values_list('preco_venda', flat=True)
        .first()
    )
    return render(request, 'produtos/produto_inativar_confirm.html', {
        'produto': produto,
        'codigos_ativos': codigos_ativos,
        'preco_ref': preco_ref,
    })
