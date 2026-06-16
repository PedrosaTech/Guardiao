"""
Modelos do módulo de eventos.
"""
from django.db import models
from django.conf import settings
from core.models import BaseModel, Empresa, Loja
from core.fields import EncryptedCharField
from crm.models import Lead
from pessoas.models import Cliente
from vendas.models import PedidoVenda


class EventoVenda(BaseModel):
    """
    Evento de venda externa.
    
    Gerencia vendas para eventos como São João, Réveillon, Casamentos, etc.
    """
    
    TIPO_EVENTO_CHOICES = [
        ('SAO_JOAO', 'São João'),
        ('REVEILLON', 'Réveillon'),
        ('CASAMENTO', 'Casamento'),
        ('CORPORATIVO', 'Corporativo'),
        ('RELIGIOSO', 'Religioso'),
        ('OUTRO', 'Outro'),
    ]
    
    STATUS_CHOICES = [
        ('RASCUNHO', 'Rascunho'),
        ('PROPOSTA_ENVIADA', 'Proposta Enviada'),
        ('APROVADO', 'Aprovado'),
        ('EM_EXECUCAO', 'Em Execução'),
        ('CONCLUIDO', 'Concluído'),
        ('CANCELADO', 'Cancelado'),
    ]
    
    empresa = models.ForeignKey(
        Empresa,
        on_delete=models.CASCADE,
        related_name='eventos_venda',
        verbose_name='Empresa',
    )
    loja = models.ForeignKey(
        Loja,
        on_delete=models.PROTECT,
        related_name='eventos_venda',
        verbose_name='Loja',
    )
    lead = models.ForeignKey(
        Lead,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='eventos',
        verbose_name='Lead',
    )
    cliente = models.ForeignKey(
        Cliente,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='eventos',
        verbose_name='Cliente',
    )
    pedido = models.ForeignKey(
        PedidoVenda,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='eventos',
        verbose_name='Pedido de Venda',
    )
    
    nome_evento = models.CharField('Nome do Evento', max_length=255)
    tipo_evento = models.CharField('Tipo de Evento', max_length=20, choices=TIPO_EVENTO_CHOICES)
    data_evento = models.DateField('Data do Evento')
    hora_evento = models.TimeField('Hora do Evento', null=True, blank=True)
    
    # Endereço do evento
    endereco_logradouro = models.CharField('Logradouro', max_length=255)
    endereco_numero = models.CharField('Número', max_length=20)
    endereco_complemento = models.CharField('Complemento', max_length=100, blank=True, null=True)
    endereco_bairro = models.CharField('Bairro', max_length=100)
    endereco_cidade = models.CharField('Cidade', max_length=100)
    endereco_uf = models.CharField('UF', max_length=2)
    endereco_cep = models.CharField('CEP', max_length=10)
    
    estimativa_publico = models.IntegerField('Estimativa de Público', null=True, blank=True)
    responsavel_evento = models.CharField('Responsável pelo Evento', max_length=255)
    telefone_responsavel = EncryptedCharField('Telefone do Responsável', max_length=255)
    equipe_responsavel = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        related_name='eventos_responsavel',
        verbose_name='Equipe Responsável',
    )
    
    status = models.CharField('Status', max_length=20, choices=STATUS_CHOICES, default='RASCUNHO')
    observacoes = models.TextField('Observações', blank=True)
    
    class Meta:
        verbose_name = 'Evento de Venda'
        verbose_name_plural = 'Eventos de Venda'
        ordering = ['-data_evento', '-created_at']
        indexes = [
            models.Index(fields=['empresa', 'status']),
            models.Index(fields=['loja', 'data_evento']),
            models.Index(fields=['tipo_evento', 'data_evento']),
            models.Index(fields=['status', 'data_evento']),
        ]
    
    def __str__(self):
        return f"{self.nome_evento} - {self.get_tipo_evento_display()} - {self.data_evento}"
    
    def gerar_pedido_evento(self, condicao_pagamento=None, cliente=None) -> PedidoVenda:
        """
        Gera ou retorna o pedido de venda associado ao evento.
        
        TODO: Futuramente, os itens do pedido serão montados a partir de uma tela de proposta de evento.
        TODO: Futuramente, ao "faturar", vamos criar uma NotaFiscalSaida relacionada a esse EventoVenda.
        
        Args:
            condicao_pagamento: CondicaoPagamento opcional (se None, busca ou cria padrão)
            cliente: Cliente opcional (se não informado, usa self.cliente ou cria genérico)
        
        Returns:
            PedidoVenda associado ao evento
        """
        # Se já existe pedido, retorna
        if self.pedido:
            return self.pedido
        
        # Define cliente
        cliente_final = cliente if cliente is not None else self.cliente
        
        # Se não houver cliente, cria ou busca cliente genérico "Consumidor Final"
        if not cliente_final:
            from pessoas.models import Cliente
            cliente_final, _ = Cliente.objects.get_or_create(
                empresa=self.empresa,
                tipo_pessoa='PF',
                nome_razao_social='Consumidor Final',
                cpf_cnpj='00000000000',
                defaults={
                    'created_by': self.created_by,
                }
            )
        
        # Busca ou cria condição de pagamento padrão (à vista) se não informada
        if not condicao_pagamento:
            from vendas.models import CondicaoPagamento
            condicao_pagamento = CondicaoPagamento.objects.filter(
                empresa=self.empresa,
                nome__icontains='vista',
                is_active=True
            ).first()
            
            if not condicao_pagamento:
                condicao_pagamento = CondicaoPagamento.objects.create(
                    empresa=self.empresa,
                    nome='À Vista',
                    numero_parcelas=1,
                    dias_entre_parcelas=0,
                    created_by=self.created_by,
                )
        
        # Define vendedor (usa created_by se disponível)
        vendedor = self.created_by if self.created_by else None
        
        # Se ainda não houver vendedor, tenta buscar um usuário ativo da empresa
        # Por enquanto, vamos exigir que created_by exista
        if not vendedor:
            # TODO: Vincular vendedor específico depois ou buscar da equipe_responsavel
            # Por enquanto, vamos usar o primeiro usuário da equipe se houver
            if self.equipe_responsavel.exists():
                vendedor = self.equipe_responsavel.first()
            else:
                # Último recurso: buscar qualquer usuário ativo
                from django.contrib.auth import get_user_model
                User = get_user_model()
                vendedor = User.objects.filter(is_active=True).first()
        
        if not vendedor:
            raise ValueError(
                f"Não foi possível determinar o vendedor para o evento '{self.nome_evento}'. "
                "É necessário ter um usuário criador ou equipe responsável."
            )
        
        # Cria o pedido
        pedido = PedidoVenda.objects.create(
            loja=self.loja,
            cliente=cliente_final,
            tipo_venda='EVENTO',
            status='ORCAMENTO',  # Fase de proposta
            vendedor=vendedor,
            condicao_pagamento=condicao_pagamento,
            valor_total=0,  # Será recalculado depois com os itens
            created_by=self.created_by,
        )
        
        # Associa o pedido ao evento
        self.pedido = pedido
        self.save(update_fields=['pedido', 'updated_at'])
        
        return pedido

