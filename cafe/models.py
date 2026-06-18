from django.db import models

from core.models import BaseModel, Loja


class CategoriaCafe(BaseModel):
    """Categorias do cardápio: Bebidas Quentes, Frios, Lanches, etc."""

    nome = models.CharField('Categoria', max_length=50)
    ordem = models.PositiveIntegerField('Ordem de exibição', default=0)
    icone = models.CharField('Ícone (emoji)', max_length=10, default='☕')

    class Meta:
        ordering = ['ordem', 'nome']
        verbose_name = 'Categoria do Café'
        verbose_name_plural = 'Categorias do Café'

    def __str__(self):
        return f'{self.icone} {self.nome}'


class ItemCardapio(BaseModel):
    """Itens do cardápio do Café Al-qui-mia."""

    DISPONIBILIDADE_CHOICES = [
        ('DISPONIVEL', 'Disponível'),
        ('INDISPONIVEL', 'Indisponível'),
        ('SAZONAL', 'Sazonal'),
    ]

    categoria = models.ForeignKey(
        CategoriaCafe, on_delete=models.PROTECT, related_name='itens'
    )
    nome = models.CharField('Nome do Item', max_length=100)
    icone = models.CharField(
        'Ícone (emoji)',
        max_length=10,
        blank=True,
        help_text='Deixe vazio para usar o ícone da categoria',
    )
    descricao = models.TextField('Descrição', blank=True)
    ingredientes = models.TextField(
        'Ingredientes',
        blank=True,
        help_text='Ingredientes principais, separados por vírgula',
    )
    preco = models.DecimalField('Preço', max_digits=8, decimal_places=2)
    disponibilidade = models.CharField(
        max_length=20, choices=DISPONIBILIDADE_CHOICES, default='DISPONIVEL'
    )
    destaque = models.BooleanField('Destaque no cardápio', default=False)
    vegano = models.BooleanField('Vegano', default=False)
    sem_gluten = models.BooleanField('Sem Glúten', default=False)
    ordem = models.PositiveIntegerField('Ordem de exibição', default=0)
    tempo_preparo = models.PositiveIntegerField('Tempo de preparo (min)', default=5)

    class Meta:
        ordering = ['categoria__ordem', 'ordem', 'nome']
        verbose_name = 'Item do Cardápio'
        verbose_name_plural = 'Itens do Cardápio'

    @property
    def icone_exibicao(self):
        return self.icone or self.categoria.icone

    def __str__(self):
        return f'{self.nome} — R$ {self.preco}'


class Comanda(BaseModel):
    STATUS_CHOICES = [
        ('ABERTA', 'Aberta'),
        ('FECHADA', 'Fechada'),
        ('CANCELADA', 'Cancelada'),
    ]
    loja = models.ForeignKey(Loja, on_delete=models.PROTECT, related_name='comandas')
    nome_cliente = models.CharField('Nome do Cliente', max_length=100)
    cpf_cliente = models.CharField('CPF', max_length=14, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='ABERTA')
    observacao = models.TextField('Observação', blank=True)
    valor_total = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    forma_pagamento = models.CharField(max_length=20, blank=True)
    data_fechamento = models.DateTimeField(null=True, blank=True)
    numero = models.PositiveIntegerField('Número da Comanda', blank=True, null=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Comanda'
        verbose_name_plural = 'Comandas'
        constraints = [
            models.UniqueConstraint(
                fields=['loja', 'numero'],
                name='cafe_comanda_loja_numero_unique',
            ),
        ]

    def __str__(self):
        return f'#{self.numero} — {self.nome_cliente}'

    def calcular_total(self):
        total = sum(i.subtotal for i in self.itens.filter(is_active=True))
        self.valor_total = total
        self.save(update_fields=['valor_total', 'updated_at'])
        return total


class ItemComanda(BaseModel):
    comanda = models.ForeignKey(Comanda, on_delete=models.CASCADE, related_name='itens')
    item_cardapio = models.ForeignKey(ItemCardapio, on_delete=models.PROTECT)
    descricao = models.CharField(max_length=120)
    quantidade = models.DecimalField(max_digits=8, decimal_places=2, default=1)
    valor_unitario = models.DecimalField(max_digits=10, decimal_places=2)
    subtotal = models.DecimalField(max_digits=10, decimal_places=2)
    observacao = models.CharField('Obs do item', max_length=200, blank=True)

    class Meta:
        verbose_name = 'Item da Comanda'
        verbose_name_plural = 'Itens da Comanda'

    def save(self, *args, **kwargs):
        if self.item_cardapio_id:
            if not self.descricao:
                self.descricao = self.item_cardapio.nome
            if not self.valor_unitario:
                self.valor_unitario = self.item_cardapio.preco
        self.subtotal = self.quantidade * self.valor_unitario
        super().save(*args, **kwargs)
