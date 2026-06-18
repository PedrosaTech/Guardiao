import base64
import io
import urllib.parse
from decimal import Decimal, InvalidOperation

import qrcode
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Max, Prefetch, Q
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST

from core.models import Loja
from core.tenant import get_empresa_ativa

from .models import CategoriaCafe, Comanda, ItemCardapio, ItemComanda


def _parse_decimal(valor: str) -> Decimal:
    s = str(valor).strip().replace('R$', '').strip()
    if ',' in s:
        s = s.replace('.', '').replace(',', '.')
    return Decimal(s)


def _get_loja_cafe(request) -> Loja:
    empresa = get_empresa_ativa(request)
    loja = (
        Loja.objects.filter(empresa=empresa, is_active=True)
        .order_by('pk')
        .first()
    )
    if not loja:
        raise Http404('Nenhuma loja ativa para a empresa selecionada.')
    return loja


def _comanda_queryset(request):
    loja = _get_loja_cafe(request)
    return Comanda.objects.filter(loja=loja, is_active=True)


def _reservar_numero_comanda(loja) -> int:
    with transaction.atomic():
        max_num = (
            Comanda.objects.select_for_update()
            .filter(loja=loja)
            .aggregate(Max('numero'))['numero__max']
            or 0
        )
        return max_num + 1


def _tempo_aberto(comanda):
    delta = timezone.now() - comanda.created_at
    horas = int(delta.total_seconds() // 3600)
    minutos = int((delta.total_seconds() % 3600) // 60)
    if horas:
        return f'{horas}h {minutos}min'
    return f'{minutos} min'


def _cardapio_queryset(filtro_disponivel=None):
    qs = ItemCardapio.objects.filter(is_active=True).select_related('categoria')
    if filtro_disponivel == 'disponivel':
        qs = qs.filter(disponibilidade='DISPONIVEL')
    elif filtro_disponivel == 'indisponivel':
        qs = qs.filter(disponibilidade='INDISPONIVEL')
    return qs


def _categorias_com_itens(filtro_disponivel=None):
    itens_qs = _cardapio_queryset(filtro_disponivel)
    return (
        CategoriaCafe.objects.filter(is_active=True)
        .prefetch_related(Prefetch('itens', queryset=itens_qs))
        .order_by('ordem', 'nome')
    )


def _adicionar_item_comanda(comanda, item_id, quantidade, observacao, user):
    item_cardapio = get_object_or_404(
        ItemCardapio,
        pk=item_id,
        is_active=True,
        disponibilidade='DISPONIVEL',
    )
    ItemComanda.objects.create(
        comanda=comanda,
        item_cardapio=item_cardapio,
        descricao=item_cardapio.nome,
        quantidade=quantidade,
        valor_unitario=item_cardapio.preco,
        observacao=observacao,
        created_by=user,
    )
    comanda.calcular_total()
    return item_cardapio


# --- Comandas ---


@login_required
def lista_comandas(request):
    filtro = request.GET.get('filtro', 'abertas')
    qs = _comanda_queryset(request)

    hoje = timezone.localdate()
    if filtro == 'fechadas_hoje':
        comandas = qs.filter(status='FECHADA', data_fechamento__date=hoje)
    else:
        comandas = qs.filter(status='ABERTA')

    comandas = comandas.prefetch_related('itens')
    lista = [{'obj': c, 'tempo_aberto': _tempo_aberto(c)} for c in comandas]

    return render(request, 'cafe/lista_comandas.html', {
        'comandas': lista,
        'filtro': filtro,
    })


@login_required
@require_http_methods(['GET', 'POST'])
def nova_comanda(request):
    loja = _get_loja_cafe(request)

    if request.method == 'POST':
        nome = request.POST.get('nome_cliente', '').strip()
        if not nome:
            messages.error(request, 'Informe o nome do cliente.')
            return render(request, 'cafe/nova_comanda.html')

        comanda = Comanda(
            loja=loja,
            nome_cliente=nome,
            cpf_cliente=request.POST.get('cpf_cliente', '').strip(),
            observacao=request.POST.get('observacao', '').strip(),
            created_by=request.user,
        )
        comanda.numero = _reservar_numero_comanda(loja)
        comanda.save()
        messages.success(request, f'Comanda #{comanda.numero} aberta.')
        return redirect('cafe:detalhe', pk=comanda.pk)

    return render(request, 'cafe/nova_comanda.html')


@login_required
def comanda_detalhe(request, pk):
    comanda = get_object_or_404(
        _comanda_queryset(request).prefetch_related('itens__item_cardapio'),
        pk=pk,
    )
    itens = comanda.itens.filter(is_active=True).order_by('created_at')
    return render(request, 'cafe/comanda_detalhe.html', {
        'comanda': comanda,
        'itens': itens,
        'tempo_aberto': _tempo_aberto(comanda),
    })


@login_required
@require_http_methods(['GET', 'POST'])
def adicionar_item(request, pk):
    comanda = get_object_or_404(_comanda_queryset(request), pk=pk, status='ABERTA')

    if request.method == 'POST':
        item_id = request.POST.get('item_id')
        quantidade_raw = request.POST.get('quantidade', '1').replace(',', '.')
        observacao = request.POST.get('observacao', '').strip()

        try:
            quantidade = Decimal(quantidade_raw)
            if quantidade <= 0:
                raise InvalidOperation
        except (InvalidOperation, ValueError):
            messages.error(request, 'Quantidade inválida.')
            return redirect('cafe:adicionar_item', pk=pk)

        item_cardapio = _adicionar_item_comanda(
            comanda, item_id, quantidade, observacao, request.user
        )
        messages.success(request, f'{item_cardapio.nome} adicionado.')
        return redirect('cafe:detalhe', pk=pk)

    categorias = _categorias_com_itens('disponivel')
    itens_count = comanda.itens.filter(is_active=True).count()
    return render(request, 'cafe/adicionar_item.html', {
        'comanda': comanda,
        'categorias': categorias,
        'itens_count': itens_count,
    })


@login_required
@require_POST
def adicionar_item_rapido(request, pk):
    comanda = get_object_or_404(_comanda_queryset(request), pk=pk, status='ABERTA')
    item_id = request.POST.get('item_id')
    quantidade_raw = request.POST.get('quantidade', '1').replace(',', '.')
    observacao = request.POST.get('observacao', '').strip()

    try:
        quantidade = Decimal(quantidade_raw)
        if quantidade <= 0:
            raise InvalidOperation
    except (InvalidOperation, ValueError):
        return JsonResponse({'ok': False, 'erro': 'Quantidade inválida.'}, status=400)

    item_cardapio = _adicionar_item_comanda(
        comanda, item_id, quantidade, observacao, request.user
    )
    itens_count = comanda.itens.filter(is_active=True).count()
    return JsonResponse({
        'ok': True,
        'nome': item_cardapio.nome,
        'icone': item_cardapio.icone_exibicao,
        'preco': str(item_cardapio.preco),
        'total': str(comanda.valor_total),
        'itens_count': itens_count,
    })


@login_required
@require_http_methods(['GET', 'POST'])
def fechar_conta(request, pk):
    comanda = get_object_or_404(
        _comanda_queryset(request).prefetch_related('itens'),
        pk=pk,
        status='ABERTA',
    )
    itens = comanda.itens.filter(is_active=True).order_by('created_at')
    comanda.calcular_total()

    formas = [('PIX', 'PIX'), ('DINHEIRO', 'Dinheiro'), ('CARTAO', 'Cartão')]

    if request.method == 'POST':
        forma = request.POST.get('forma_pagamento', '').strip()
        if forma not in dict(formas):
            messages.error(request, 'Selecione a forma de pagamento.')
            return render(request, 'cafe/fechar_conta.html', {
                'comanda': comanda, 'itens': itens, 'formas': formas,
            })

        cpf = request.POST.get('cpf_cliente', '').strip()
        if cpf:
            comanda.cpf_cliente = cpf

        comanda.forma_pagamento = forma
        comanda.status = 'FECHADA'
        comanda.data_fechamento = timezone.now()
        comanda.updated_by = request.user
        comanda.save()
        messages.success(request, 'Conta fechada com sucesso.')
        return redirect('cafe:recibo', pk=pk)

    return render(request, 'cafe/fechar_conta.html', {
        'comanda': comanda, 'itens': itens, 'formas': formas,
    })


def _pix_qr_data_uri(comanda) -> str:
    payload = (
        f'PIX Cafe Al-qui-mia | Comanda #{comanda.numero} | '
        f'R$ {comanda.valor_total:.2f}'
    )
    img = qrcode.make(payload)
    buffer = io.BytesIO()
    img.save(buffer, format='PNG')
    b64 = base64.b64encode(buffer.getvalue()).decode('ascii')
    return f'data:image/png;base64,{b64}'


@login_required
def recibo(request, pk):
    comanda = get_object_or_404(
        _comanda_queryset(request).prefetch_related('itens'),
        pk=pk,
        status='FECHADA',
    )
    itens = comanda.itens.filter(is_active=True).order_by('created_at')

    labels_pagamento = {'PIX': 'PIX', 'DINHEIRO': 'Dinheiro', 'CARTAO': 'Cartão'}
    texto_whatsapp = (
        f'*Recibo Café Al-qui-mia*\n'
        f'Comanda #{comanda.numero}\n'
        f'Cliente: {comanda.nome_cliente}\n'
        f'Total: R$ {comanda.valor_total:.2f}\n'
        f'Pagamento: {labels_pagamento.get(comanda.forma_pagamento, comanda.forma_pagamento)}'
    )
    whatsapp_url = f'https://wa.me/?text={urllib.parse.quote(texto_whatsapp)}'
    pix_qr = _pix_qr_data_uri(comanda) if comanda.forma_pagamento == 'PIX' else None

    return render(request, 'cafe/recibo.html', {
        'comanda': comanda,
        'itens': itens,
        'whatsapp_url': whatsapp_url,
        'pix_qr': pix_qr,
        'labels_pagamento': labels_pagamento,
        'forma_label': labels_pagamento.get(comanda.forma_pagamento, comanda.forma_pagamento),
    })


@login_required
@require_POST
def cancelar_item(request, item_pk):
    loja = _get_loja_cafe(request)
    item = get_object_or_404(
        ItemComanda.objects.select_related('comanda'),
        pk=item_pk,
        is_active=True,
        comanda__status='ABERTA',
        comanda__loja=loja,
    )
    comanda = item.comanda
    item.is_active = False
    item.updated_by = request.user
    item.save(update_fields=['is_active', 'updated_by', 'updated_at'])
    comanda.calcular_total()
    messages.success(request, 'Item removido da comanda.')
    return redirect('cafe:detalhe', pk=comanda.pk)


@login_required
@require_http_methods(['GET'])
def buscar_produtos(request):
    q = request.GET.get('q', '').strip()
    if len(q) < 2:
        return JsonResponse({'itens': []})

    itens = ItemCardapio.objects.filter(
        Q(nome__icontains=q) | Q(descricao__icontains=q),
        disponibilidade='DISPONIVEL',
        is_active=True,
    ).select_related('categoria')[:10]

    data = [
        {
            'id': i.id,
            'nome': i.nome,
            'preco': str(i.preco),
            'categoria': str(i.categoria),
            'vegano': i.vegano,
            'sem_gluten': i.sem_gluten,
            'tempo_preparo': i.tempo_preparo,
        }
        for i in itens
    ]
    return JsonResponse({'itens': data})


# --- Cardápio ---


@login_required
def lista_cardapio(request):
    filtro = request.GET.get('disponivel', 'todos')
    categorias = _categorias_com_itens(
        None if filtro == 'todos' else ('disponivel' if filtro == 'sim' else 'indisponivel')
    )
    return render(request, 'cafe/lista_cardapio.html', {
        'categorias': categorias,
        'filtro': filtro,
    })


@login_required
@require_http_methods(['GET', 'POST'])
def nova_categoria(request):
    if request.method == 'POST':
        nome = request.POST.get('nome', '').strip()
        if not nome:
            messages.error(request, 'Informe o nome da categoria.')
            return render(request, 'cafe/nova_categoria.html')

        CategoriaCafe.objects.create(
            nome=nome,
            icone=request.POST.get('icone', '☕').strip() or '☕',
            ordem=int(request.POST.get('ordem') or 0),
            created_by=request.user,
        )
        messages.success(request, 'Categoria criada.')
        return redirect('cafe:cardapio')

    return render(request, 'cafe/nova_categoria.html')


@login_required
@require_http_methods(['GET', 'POST'])
def editar_categoria(request, pk):
    categoria = get_object_or_404(CategoriaCafe, pk=pk, is_active=True)

    if request.method == 'POST':
        nome = request.POST.get('nome', '').strip()
        if not nome:
            messages.error(request, 'Informe o nome da categoria.')
            return render(request, 'cafe/editar_categoria.html', {'categoria': categoria})

        categoria.nome = nome
        categoria.icone = request.POST.get('icone', '☕').strip() or '☕'
        categoria.ordem = int(request.POST.get('ordem') or 0)
        categoria.updated_by = request.user
        categoria.save()
        messages.success(request, 'Categoria atualizada.')
        return redirect('cafe:cardapio')

    return render(request, 'cafe/editar_categoria.html', {'categoria': categoria})


def _salvar_item_cardapio(request, item=None):
    categoria_id = request.POST.get('categoria')
    nome = request.POST.get('nome', '').strip()
    if not nome or not categoria_id:
        messages.error(request, 'Nome e categoria são obrigatórios.')
        return False

    try:
        preco = _parse_decimal(request.POST.get('preco', '0'))
    except (InvalidOperation, ValueError):
        messages.error(request, 'Preço inválido.')
        return False

    categoria = get_object_or_404(CategoriaCafe, pk=categoria_id, is_active=True)
    dados = {
        'categoria': categoria,
        'nome': nome,
        'icone': request.POST.get('icone', '').strip(),
        'descricao': request.POST.get('descricao', '').strip(),
        'ingredientes': request.POST.get('ingredientes', '').strip(),
        'preco': preco,
        'disponibilidade': request.POST.get('disponibilidade', 'DISPONIVEL'),
        'destaque': request.POST.get('destaque') == 'on',
        'vegano': request.POST.get('vegano') == 'on',
        'sem_gluten': request.POST.get('sem_gluten') == 'on',
        'ordem': int(request.POST.get('ordem') or 0),
        'tempo_preparo': int(request.POST.get('tempo_preparo') or 5),
    }

    if item:
        for k, v in dados.items():
            setattr(item, k, v)
        item.updated_by = request.user
        item.save()
    else:
        ItemCardapio.objects.create(**dados, created_by=request.user)
    return True


@login_required
@require_http_methods(['GET', 'POST'])
def novo_item_cardapio(request):
    categorias = CategoriaCafe.objects.filter(is_active=True).order_by('ordem', 'nome')

    if request.method == 'POST':
        if _salvar_item_cardapio(request):
            messages.success(request, 'Item adicionado ao cardápio.')
            return redirect('cafe:cardapio')
        return render(request, 'cafe/novo_item_cardapio.html', {
            'categorias': categorias,
            'disponibilidade_choices': ItemCardapio.DISPONIBILIDADE_CHOICES,
        })

    return render(request, 'cafe/novo_item_cardapio.html', {
        'categorias': categorias,
        'disponibilidade_choices': ItemCardapio.DISPONIBILIDADE_CHOICES,
    })


@login_required
@require_http_methods(['GET', 'POST'])
def editar_item_cardapio(request, pk):
    item = get_object_or_404(ItemCardapio, pk=pk, is_active=True)
    categorias = CategoriaCafe.objects.filter(is_active=True).order_by('ordem', 'nome')

    if request.method == 'POST':
        if _salvar_item_cardapio(request, item=item):
            messages.success(request, 'Item atualizado.')
            return redirect('cafe:cardapio')
        return render(request, 'cafe/editar_item_cardapio.html', {
            'item': item,
            'categorias': categorias,
            'disponibilidade_choices': ItemCardapio.DISPONIBILIDADE_CHOICES,
        })

    return render(request, 'cafe/editar_item_cardapio.html', {
        'item': item,
        'categorias': categorias,
        'disponibilidade_choices': ItemCardapio.DISPONIBILIDADE_CHOICES,
    })


@login_required
@require_POST
def toggle_disponibilidade(request, pk):
    item = get_object_or_404(ItemCardapio, pk=pk, is_active=True)
    if item.disponibilidade == 'DISPONIVEL':
        item.disponibilidade = 'INDISPONIVEL'
    else:
        item.disponibilidade = 'DISPONIVEL'
    item.updated_by = request.user
    item.save(update_fields=['disponibilidade', 'updated_by', 'updated_at'])

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({
            'ok': True,
            'disponibilidade': item.disponibilidade,
            'label': item.get_disponibilidade_display(),
        })

    messages.success(request, f'{item.nome}: {item.get_disponibilidade_display()}.')
    return redirect('cafe:cardapio')


def cardapio_publico(request):
    categorias = _categorias_com_itens()
    return render(request, 'cafe/cardapio_publico.html', {'categorias': categorias})
