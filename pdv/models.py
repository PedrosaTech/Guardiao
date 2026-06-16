"""
Modelos do módulo PDV (Ponto de Venda).
"""
from django.db import models
from django.core.validators import MinValueValidator
from django.conf import settings
from decimal import Decimal
from core.models import BaseModel, Loja
from vendas.models import PedidoVenda


class CaixaSessao(BaseModel):
    """
    Sessão de caixa (abertura e fechamento).
    """
    
    STATUS_CHOICES = [
        ('ABERTO', 'Aberto'),
        ('FECHADO', 'Fechado'),
    ]
    
    loja = models.ForeignKey(
        Loja,
        on_delete=models.PROTECT,
        related_name='sessoes_caixa',
        verbose_name='Loja',
    )
    usuario_abertura = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='sessoes_caixa_abertas',
        verbose_name='Usuário de Abertura',
    )
    data_hora_abertura = models.DateTimeField('Data/Hora de Abertura', auto_now_add=True)
    saldo_inicial = models.DecimalField(
        'Saldo Inicial',
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))]
    )
    usuario_fechamento = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='sessoes_caixa_fechadas',
        verbose_name='Usuário de Fechamento',
    )
    data_hora_fechamento = models.DateTimeField('Data/Hora de Fechamento', null=True, blank=True)
    saldo_final = models.DecimalField(
        'Saldo Final',
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal('0.00'))]
    )
    status = models.CharField('Status', max_length=10, choices=STATUS_CHOICES, default='ABERTO')
    
    class Meta:
        verbose_name = 'Sessão de Caixa'
        verbose_name_plural = 'Sessões de Caixa'
        ordering = ['-data_hora_abertura']
        indexes = [
            models.Index(fields=['loja', 'status']),
            models.Index(fields=['usuario_abertura', '-data_hora_abertura']),
        ]
    
    def __str__(self):
        return f"Caixa {self.loja.nome} - {self.data_hora_abertura} - {self.status}"


class Pagamento(BaseModel):
    """
    Pagamento de um pedido de venda.
    """
    
    TIPO_CHOICES = [
        ('DINHEIRO', 'Dinheiro'),
        ('PIX', 'PIX'),
        ('CARTAO_CREDITO', 'Cartão de Crédito'),
        ('CARTAO_DEBITO', 'Cartão de Débito'),
    ]
    
    pedido = models.ForeignKey(
        PedidoVenda,
        on_delete=models.CASCADE,
        related_name='pagamentos',
        verbose_name='Pedido',
    )
    caixa_sessao = models.ForeignKey(
        CaixaSessao,
        on_delete=models.PROTECT,
        related_name='pagamentos',
        verbose_name='Sessão de Caixa',
    )
    tipo = models.CharField('Tipo de Pagamento', max_length=20, choices=TIPO_CHOICES)
    valor = models.DecimalField(
        'Valor',
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))]
    )
    
    class Meta:
        verbose_name = 'Pagamento'
        verbose_name_plural = 'Pagamentos'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['pedido']),
            models.Index(fields=['caixa_sessao', '-created_at']),
        ]
    
    def __str__(self):
        return f"{self.pedido} - {self.tipo} - {self.valor}"
