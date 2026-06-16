"""
Modelos do módulo fiscal - NF-e / NFC-e.
"""
from django.conf import settings
from django.db import models
from django.core.validators import MinValueValidator
from decimal import Decimal
from core.models import BaseModel, Loja
from core.fields import EncryptedCharField
from pessoas.models import Cliente, Fornecedor
from produtos.models import Produto


class ConfiguracaoFiscalLoja(BaseModel):
    """
    Configuração fiscal de uma loja para emissão de NF-e / NFC-e.
    
    TODO: Integração com SEFAZ-BA (NF-e/NFC-e)
    TODO: Armazenamento seguro do certificado digital (usar FileField com criptografia)
    TODO: Validação de certificado antes de salvar
    TODO: Implementar renovação automática de certificado
    """
    
    AMBIENTE_CHOICES = [
        ('HOMOLOGACAO', 'Homologação'),
        ('PRODUCAO', 'Produção'),
    ]
    
    loja = models.OneToOneField(
        Loja,
        on_delete=models.CASCADE,
        related_name='configuracao_fiscal',
        verbose_name='Loja',
    )
    cnpj = EncryptedCharField('CNPJ', max_length=255)  # 255 para valor criptografado no DB
    inscricao_estadual = models.CharField('Inscrição Estadual', max_length=20)
    regime_tributario = models.CharField(
        'Regime Tributário',
        max_length=50,
        help_text='Ex: SIMPLES_NACIONAL, LUCRO_PRESUMIDO, LUCRO_REAL'
    )
    
    # Certificado Digital
    # TODO: Em produção, usar FileField com armazenamento seguro (ex: S3 com criptografia)
    certificado_arquivo = models.CharField('Caminho do Certificado', max_length=500, blank=True, null=True)
    senha_certificado = EncryptedCharField('Senha do Certificado', max_length=255, blank=True, null=True)
    
    ambiente = models.CharField('Ambiente', max_length=20, choices=AMBIENTE_CHOICES, default='HOMOLOGACAO')
    serie_nfe = models.CharField('Série NF-e', max_length=3, default='001')
    serie_nfce = models.CharField('Série NFC-e', max_length=3, default='001')
    proximo_numero_nfe = models.IntegerField('Próximo Número NF-e', default=1)
    proximo_numero_nfce = models.IntegerField('Próximo Número NFC-e', default=1)

    # NFS-e Nacional
    inscricao_municipal = models.CharField('Inscrição Municipal', max_length=20, blank=True)
    codigo_cnae = models.CharField('CNAE Principal', max_length=7, blank=True)
    serie_rps = models.CharField('Série RPS', max_length=5, default='RPS')
    proximo_numero_rps = models.IntegerField('Próximo Número RPS', default=1)

    # NFC-e (CSC para QR Code)
    csc_id = models.CharField('CSC ID (NFC-e)', max_length=6, blank=True)
    csc_token = models.CharField('CSC Token (NFC-e)', max_length=36, blank=True)
    
    # ═══════════════════════════════════════════════════════════
    # REFORMA TRIBUTÁRIA 2026
    # ═══════════════════════════════════════════════════════════
    
    usar_reforma_2026 = models.BooleanField(
        'Ativar Reforma 2026',
        default=False,  # CRÍTICO: começa desligado
        help_text=(
            'Ativa o cálculo de CBS e IBS conforme Reforma Tributária. '
            'Desligado = sistema funciona como antes. '
            'Ligado = inclui CBS/IBS nos cálculos e notas.'
        )
    )
    
    aliquota_ibs_padrao_2026 = models.DecimalField(
        'Alíquota IBS Padrão 2026',
        max_digits=5,
        decimal_places=2,
        default=Decimal('0.10'),
        help_text='Alíquota padrão do IBS quando produto não especificar (fase teste: 0,10%)'
    )
    
    aliquota_cbs_padrao_2026 = models.DecimalField(
        'Alíquota CBS Padrão 2026',
        max_digits=5,
        decimal_places=2,
        default=Decimal('0.90'),
        help_text='Alíquota padrão da CBS quando produto não especificar (fase teste: 0,90%)'
    )
    
    class Meta:
        verbose_name = 'Configuração Fiscal da Loja'
        verbose_name_plural = 'Configurações Fiscais das Lojas'
    
    def __str__(self):
        return f"Configuração Fiscal - {self.loja.nome}"


class NotaFiscalSaida(BaseModel):
    """
    Nota Fiscal de Saída (NF-e ou NFC-e).
    
    TODO: Integração com SEFAZ-BA para emissão/autorização
    TODO: Validação de schema XML antes de salvar
    TODO: Armazenamento seguro dos XMLs (criptografia)
    TODO: Possibilidade de exportação para fiscalização
    TODO: Implementar cancelamento e carta de correção
    """
    
    TIPO_DOCUMENTO_CHOICES = [
        ('NFE', 'NF-e'),
        ('NFCE', 'NFC-e'),
    ]
    
    STATUS_CHOICES = [
        ('RASCUNHO', 'Rascunho'),
        ('EM_PROCESSAMENTO', 'Em Processamento'),
        ('AUTORIZADA', 'Autorizada'),
        ('REJEITADA', 'Rejeitada'),
        ('CANCELADA', 'Cancelada'),
    ]
    
    loja = models.ForeignKey(
        Loja,
        on_delete=models.PROTECT,
        related_name='notas_fiscais_saida',
        verbose_name='Loja',
    )
    cliente = models.ForeignKey(
        Cliente,
        on_delete=models.PROTECT,
        related_name='notas_fiscais',
        verbose_name='Cliente',
    )
    pedido_venda = models.ForeignKey(
        'vendas.PedidoVenda',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='notas_fiscais',
        verbose_name='Pedido de Venda',
    )
    evento = models.ForeignKey(
        'eventos.EventoVenda',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='notas_fiscais',
        verbose_name='Evento',
    )
    
    tipo_documento = models.CharField('Tipo de Documento', max_length=4, choices=TIPO_DOCUMENTO_CHOICES)
    numero = models.IntegerField('Número')
    serie = models.CharField('Série', max_length=3)
    chave_acesso = models.CharField('Chave de Acesso', max_length=44, blank=True, null=True)
    valor_total = models.DecimalField(
        'Valor Total',
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))]
    )
    xml_arquivo = models.TextField('XML da Nota', blank=True, null=True)
    status = models.CharField('Status', max_length=20, choices=STATUS_CHOICES, default='RASCUNHO')
    data_emissao = models.DateTimeField('Data de Emissão', null=True, blank=True)
    motivo_cancelamento = models.TextField('Motivo do Cancelamento', blank=True, null=True)
    
    # ═══════════════════════════════════════════════════════════
    # REFORMA TRIBUTÁRIA 2026 - Cache de Impostos
    # Valores CONGELADOS no momento da autorização
    # ═══════════════════════════════════════════════════════════
    
    base_ibs_total = models.DecimalField(
        'Base IBS Total (Cache)',
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True,
        help_text='Valor CONGELADO no momento da autorização - não recalcular'
    )
    
    valor_ibs_total = models.DecimalField(
        'Valor IBS Total (Cache)',
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True
    )
    
    base_cbs_total = models.DecimalField(
        'Base CBS Total (Cache)',
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True
    )
    
    valor_cbs_total = models.DecimalField(
        'Valor CBS Total (Cache)',
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True
    )
    
    # Snapshot completo dos impostos por item (JSON)
    # Armazena estado imutável dos impostos no momento da autorização
    impostos_snapshot = models.JSONField(
        'Snapshot Impostos',
        null=True,
        blank=True,
        help_text='JSON com impostos por item no momento da autorização (imutável)'
    )
    
    class Meta:
        verbose_name = 'Nota Fiscal de Saída'
        verbose_name_plural = 'Notas Fiscais de Saída'
        ordering = ['-data_emissao', '-numero']
        unique_together = [['loja', 'tipo_documento', 'serie', 'numero']]
        indexes = [
            models.Index(fields=['loja', 'status']),
            models.Index(fields=['cliente', '-data_emissao']),
            models.Index(fields=['chave_acesso']),
        ]
    
    def gravar_snapshot_impostos(self, config_fiscal=None):
        """
        Grava snapshot dos impostos no momento da autorização.
        
        IMPORTANTE: Após autorização, valores não devem ser recalculados.
        Este método deve ser chamado APENAS quando a nota for autorizada pela SEFAZ.
        
        Args:
            config_fiscal: ConfiguracaoFiscalLoja (opcional, busca automaticamente se None)
        """
        from fiscal.calculos import calcular_impostos_nota, calcular_impostos_item
        
        if not self.pedido_venda:
            raise ValueError("Nota deve ter pedido_venda para gravar snapshot")
        
        # Buscar config se não fornecida
        if not config_fiscal:
            try:
                config_fiscal = self.loja.configuracao_fiscal
            except:
                config_fiscal = None
        
        itens = self.pedido_venda.itens.filter(is_active=True)
        regime = config_fiscal.regime_tributario if config_fiscal else None
        
        # Calcular totais
        totais = calcular_impostos_nota(itens, regime, config_fiscal)
        
        # Gravar cache de totais
        self.base_ibs_total = totais.get('base_ibs', Decimal('0.00'))
        self.valor_ibs_total = totais.get('valor_ibs', Decimal('0.00'))
        self.base_cbs_total = totais.get('base_cbs', Decimal('0.00'))
        self.valor_cbs_total = totais.get('valor_cbs', Decimal('0.00'))
        
        # Gravar snapshot por item
        snapshot = []
        for item in itens:
            impostos_item = calcular_impostos_item(item, regime, config_fiscal)
            
            snapshot.append({
                'item_id': item.id,
                'produto_id': item.produto_id if hasattr(item, 'produto_id') else None,
                'servico_id': item.servico_id if hasattr(item, 'servico_id') else None,
                'descricao': item.get_descricao() if hasattr(item, 'get_descricao') else (
                    item.produto.descricao if item.produto else item.servico.nome if hasattr(item, 'servico') and item.servico else 'Item'
                ),
                'quantidade': float(item.quantidade),
                'valor_unitario': float(item.preco_unitario),
                'valor_total': float(item.total),
                'impostos': {
                    k: float(v) if isinstance(v, Decimal) else v 
                    for k, v in impostos_item.items()
                }
            })
        
        self.impostos_snapshot = snapshot
        self.save(update_fields=[
            'base_ibs_total', 'valor_ibs_total', 
            'base_cbs_total', 'valor_cbs_total',
            'impostos_snapshot', 'updated_at'
        ])
    
    def get_impostos(self, recalcular=False):
        """
        Retorna impostos da nota.
        
        Lógica:
        - Se nota AUTORIZADA e tem snapshot: usa snapshot (valores imutáveis)
        - Se nota RASCUNHO ou recalcular=True: calcula em tempo real
        
        Args:
            recalcular: Se True, força recálculo mesmo se autorizada
        
        Returns:
            dict com impostos (formato igual calcular_impostos_nota)
        """
        # CORREÇÃO 3: Validar se snapshot não está vazio
        # CT-013: Recuperação graciosa de snapshot corrompido
        if (self.status == 'AUTORIZADA' and 
            self.impostos_snapshot and 
            len(self.impostos_snapshot) > 0 and 
            not recalcular):
            try:
                # Reconstruir dict de totais a partir do snapshot
                totais = {
                    'base_icms': Decimal('0.00'),
                    'valor_icms': Decimal('0.00'),
                    'base_icms_st': Decimal('0.00'),
                    'valor_icms_st': Decimal('0.00'),
                    'base_pis': Decimal('0.00'),
                    'valor_pis': Decimal('0.00'),
                    'base_cofins': Decimal('0.00'),
                    'valor_cofins': Decimal('0.00'),
                    'base_ipi': Decimal('0.00'),
                    'valor_ipi': Decimal('0.00'),
                    'base_ibs': self.base_ibs_total or Decimal('0.00'),
                    'valor_ibs': self.valor_ibs_total or Decimal('0.00'),
                    'base_cbs': self.base_cbs_total or Decimal('0.00'),
                    'valor_cbs': self.valor_cbs_total or Decimal('0.00'),
                    'valor_produtos': Decimal('0.00'),
                    'valor_frete': Decimal('0.00'),
                    'valor_seguro': Decimal('0.00'),
                    'valor_desconto': Decimal('0.00'),
                    'valor_outras_despesas': Decimal('0.00'),
                }
                
                # Somar totais do snapshot
                for item_snapshot in self.impostos_snapshot:
                    impostos = item_snapshot.get('impostos')
                    if not isinstance(impostos, dict):
                        raise ValueError("Snapshot item sem 'impostos' válido")
                    totais['base_icms'] += Decimal(str(impostos.get('base_icms', 0)))
                    totais['valor_icms'] += Decimal(str(impostos.get('valor_icms', 0)))
                    totais['base_icms_st'] += Decimal(str(impostos.get('base_icms_st', 0)))
                    totais['valor_icms_st'] += Decimal(str(impostos.get('valor_icms_st', 0)))
                    totais['base_pis'] += Decimal(str(impostos.get('base_pis', 0)))
                    totais['valor_pis'] += Decimal(str(impostos.get('valor_pis', 0)))
                    totais['base_cofins'] += Decimal(str(impostos.get('base_cofins', 0)))
                    totais['valor_cofins'] += Decimal(str(impostos.get('valor_cofins', 0)))
                    totais['base_ipi'] += Decimal(str(impostos.get('base_ipi', 0)))
                    totais['valor_ipi'] += Decimal(str(impostos.get('valor_ipi', 0)))
                    totais['valor_produtos'] += Decimal(str(item_snapshot.get('valor_total', 0)))
                
                # Adicionar flags
                config_fiscal = getattr(self.loja, 'configuracao_fiscal', None)
                regime = config_fiscal.regime_tributario if config_fiscal else None
                totais['regime_tributario'] = regime or ''
                totais['is_simples_nacional'] = regime and 'SIMPLES' in regime.upper()
                
                return totais
            except (KeyError, ValueError, TypeError, Exception) as e:
                import logging
                logging.getLogger(__name__).warning(
                    "Snapshot de impostos inválido (nota %s): %s. Recalculando.",
                    self.id, e
                )
                # Fallback: recalcular em tempo real (CT-013)
        
        # Calcular em tempo real (rascunho, forçado ou snapshot falhou)
        from fiscal.calculos import calcular_impostos_nota
        
        if not self.pedido_venda:
            return {
                'base_icms': Decimal('0.00'),
                'valor_icms': Decimal('0.00'),
                'base_icms_st': Decimal('0.00'),
                'valor_icms_st': Decimal('0.00'),
                'base_pis': Decimal('0.00'),
                'valor_pis': Decimal('0.00'),
                'base_cofins': Decimal('0.00'),
                'valor_cofins': Decimal('0.00'),
                'base_ipi': Decimal('0.00'),
                'valor_ipi': Decimal('0.00'),
                'base_ibs': Decimal('0.00'),
                'valor_ibs': Decimal('0.00'),
                'base_cbs': Decimal('0.00'),
                'valor_cbs': Decimal('0.00'),
                'valor_produtos': Decimal('0.00'),
                'valor_frete': Decimal('0.00'),
                'valor_seguro': Decimal('0.00'),
                'valor_desconto': Decimal('0.00'),
                'valor_outras_despesas': Decimal('0.00'),
                'regime_tributario': '',
                'is_simples_nacional': False,
            }
        
        config_fiscal = getattr(self.loja, 'configuracao_fiscal', None)
        itens = self.pedido_venda.itens.filter(is_active=True)
        regime = config_fiscal.regime_tributario if config_fiscal else None
        return calcular_impostos_nota(itens, regime, config_fiscal)
    
    def __str__(self):
        return f"{self.tipo_documento} {self.numero}/{self.serie} - {self.cliente.nome_razao_social}"


class NotaFiscalConsumidor(BaseModel):
    """NFC-e modelo 65 — venda ao consumidor final."""

    AMBIENTE_CHOICES = [
        ('HOMOLOGACAO', 'Homologação'),
        ('PRODUCAO', 'Produção'),
    ]
    STATUS_CHOICES = [
        ('RASCUNHO', 'Rascunho'),
        ('EM_PROCESSAMENTO', 'Em Processamento'),
        ('AUTORIZADA', 'Autorizada'),
        ('CANCELADA', 'Cancelada'),
        ('REJEITADA', 'Rejeitada'),
    ]
    MODALIDADE_CHOICES = [
        ('PRESENCIAL', 'Presencial'),
        ('ONLINE', 'Online / E-commerce'),
        ('DELIVERY', 'Delivery'),
    ]

    loja = models.ForeignKey(
        Loja,
        on_delete=models.PROTECT,
        related_name='notas_fiscais_consumidor',
        verbose_name='Loja',
    )
    numero = models.IntegerField('Número')
    serie = models.CharField('Série', max_length=3, default='001')
    chave_acesso = models.CharField('Chave de Acesso', max_length=44, blank=True)
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='RASCUNHO',
        verbose_name='Status',
    )
    ambiente = models.CharField(
        max_length=20,
        choices=AMBIENTE_CHOICES,
        default='HOMOLOGACAO',
        verbose_name='Ambiente',
    )
    modalidade = models.CharField(
        max_length=20,
        choices=MODALIDADE_CHOICES,
        default='PRESENCIAL',
        verbose_name='Modalidade',
    )

    cpf_consumidor = models.CharField('CPF do Consumidor', max_length=14, blank=True)
    nome_consumidor = models.CharField('Nome do Consumidor', max_length=60, blank=True)

    valor_produtos = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name='Valor dos Produtos',
    )
    valor_desconto = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name='Valor do Desconto',
    )
    valor_total = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name='Valor Total',
    )
    valor_icms = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name='Valor ICMS',
    )

    forma_pagamento = models.CharField(
        'Forma de Pagamento',
        max_length=20,
        default='01',
        help_text='01=Dinheiro, 03=Cartão, etc.',
    )
    valor_pago = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name='Valor Pago',
    )
    valor_troco = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name='Valor Troco',
    )

    xml_enviado = models.TextField('XML Enviado', blank=True)
    xml_retorno = models.TextField('XML Retorno', blank=True)
    protocolo = models.CharField('Protocolo', max_length=50, blank=True)
    data_autorizacao = models.DateTimeField(null=True, blank=True, verbose_name='Data de Autorização')
    motivo_rejeicao = models.TextField('Motivo da Rejeição', blank=True)

    pedido_venda = models.OneToOneField(
        'vendas.PedidoVenda',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='nfce',
        verbose_name='Pedido de Venda',
    )

    class Meta:
        unique_together = [['loja', 'serie', 'numero']]
        ordering = ['-created_at']
        verbose_name = 'NFC-e'
        verbose_name_plural = 'NFC-e'
        indexes = [
            models.Index(fields=['loja', 'status']),
            models.Index(fields=['chave_acesso']),
        ]

    def __str__(self):
        return f'NFC-e {self.numero}/{self.serie} - {self.loja.nome}'


class ItemNotaFiscalConsumidor(BaseModel):
    """Item de uma NFC-e."""

    nota = models.ForeignKey(
        NotaFiscalConsumidor,
        on_delete=models.CASCADE,
        related_name='itens',
        verbose_name='NFC-e',
    )
    produto = models.ForeignKey(
        Produto,
        on_delete=models.PROTECT,
        related_name='itens_nfce',
        verbose_name='Produto',
    )
    descricao = models.CharField(max_length=120)
    quantidade = models.DecimalField(max_digits=15, decimal_places=4)
    valor_unitario = models.DecimalField(max_digits=15, decimal_places=4)
    valor_total = models.DecimalField(max_digits=15, decimal_places=2)
    cfop = models.CharField(max_length=4, default='5102')
    ncm = models.CharField(max_length=8, blank=True)
    cst_icms = models.CharField(max_length=3, default='400')
    aliquota_icms = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0.00'))
    valor_icms = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))

    class Meta:
        verbose_name = 'Item NFC-e'
        verbose_name_plural = 'Itens NFC-e'
        ordering = ['nota', 'id']

    def __str__(self):
        return f'{self.descricao[:50]} - {self.valor_total}'


class NotaFiscalServico(BaseModel):
    """NFS-e Nacional — prestação de serviços via API nfse.gov.br."""

    STATUS_CHOICES = [
        ('RASCUNHO', 'Rascunho'),
        ('ENVIADA', 'Enviada'),
        ('AUTORIZADA', 'Autorizada'),
        ('CANCELADA', 'Cancelada'),
        ('REJEITADA', 'Rejeitada'),
    ]

    loja = models.ForeignKey(
        Loja,
        on_delete=models.PROTECT,
        related_name='notas_fiscais_servico',
        verbose_name='Loja',
    )
    numero = models.IntegerField('Número', blank=True, null=True)
    numero_rps = models.IntegerField('Número RPS')
    serie_rps = models.CharField('Série RPS', max_length=5, default='RPS')
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='RASCUNHO',
        verbose_name='Status',
    )

    cpf_cnpj_tomador = models.CharField('CPF/CNPJ Tomador', max_length=18, blank=True)
    nome_tomador = models.CharField('Nome Tomador', max_length=115)
    email_tomador = models.CharField('E-mail Tomador', max_length=80, blank=True)
    municipio_tomador = models.CharField(
        'Município Tomador (IBGE)',
        max_length=7,
        blank=True,
    )

    codigo_servico = models.CharField('Código LC 116/2003', max_length=5)
    discriminacao = models.TextField('Descrição do Serviço')
    municipio_prestacao = models.CharField('Município de Prestação (IBGE)', max_length=7)

    valor_servico = models.DecimalField(max_digits=15, decimal_places=2)
    valor_deducoes = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name='Valor Deduções',
    )
    valor_iss = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name='Valor ISS',
    )
    aliquota_iss = models.DecimalField(
        max_digits=5,
        decimal_places=4,
        default=Decimal('0.0500'),
        verbose_name='Alíquota ISS',
    )
    iss_retido = models.BooleanField('ISS Retido', default=False)
    valor_liquido = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name='Valor Líquido',
    )

    codigo_verificacao = models.CharField('Código Verificação', max_length=9, blank=True)
    link_nfse = models.URLField('Link NFS-e', blank=True)
    xml_enviado = models.TextField('XML/Payload Enviado', blank=True)
    xml_retorno = models.TextField('XML/JSON Retorno', blank=True)
    data_emissao = models.DateTimeField(null=True, blank=True, verbose_name='Data de Emissão')
    motivo_rejeicao = models.TextField('Motivo da Rejeição', blank=True)

    pedido_venda = models.ForeignKey(
        'vendas.PedidoVenda',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='nfse',
        verbose_name='Pedido de Venda',
    )

    class Meta:
        unique_together = [['loja', 'serie_rps', 'numero_rps']]
        ordering = ['-created_at']
        verbose_name = 'NFS-e'
        verbose_name_plural = 'NFS-e'
        indexes = [
            models.Index(fields=['loja', 'status']),
        ]

    def __str__(self):
        num = self.numero or self.numero_rps
        return f'NFS-e {num} - {self.nome_tomador[:40]}'


class NotaFiscalEntrada(BaseModel):
    """
    Nota Fiscal de Entrada (compra de fornecedor).
    
    Fluxo de status: RASCUNHO -> CONFIRMADA -> ESTOQUE_PARCIAL -> ESTOQUE_TOTAL
    """
    STATUS_CHOICES = [
        ('RASCUNHO', 'Rascunho'),
        ('CONFIRMADA', 'Confirmada'),
        ('ESTOQUE_PARCIAL', 'Estoque Parcial'),
        ('ESTOQUE_TOTAL', 'Estoque Total'),
    ]

    loja = models.ForeignKey(
        Loja,
        on_delete=models.PROTECT,
        related_name='notas_fiscais_entrada',
        verbose_name='Loja',
    )
    fornecedor = models.ForeignKey(
        Fornecedor,
        on_delete=models.PROTECT,
        related_name='notas_fiscais',
        verbose_name='Fornecedor',
    )
    numero = models.IntegerField('Número')
    serie = models.CharField('Série', max_length=3)
    chave_acesso = models.CharField('Chave de Acesso', max_length=44)
    valor_total = models.DecimalField(
        'Valor Total',
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))]
    )
    xml_arquivo = models.TextField('XML da Nota', blank=True, null=True)
    data_emissao = models.DateField('Data de Emissão')
    data_entrada = models.DateField('Data de Entrada')

    status = models.CharField(
        'Status',
        max_length=20,
        choices=STATUS_CHOICES,
        default='RASCUNHO',
    )
    data_entrada_estoque = models.DateTimeField(
        'Data da Entrada em Estoque',
        null=True,
        blank=True,
        help_text='Quando foi dada entrada em estoque (última execução)',
    )
    usuario_entrada_estoque = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='notas_entrada_estoque_processadas',
        verbose_name='Usuário que deu entrada em estoque',
    )
    
    class Meta:
        verbose_name = 'Nota Fiscal de Entrada'
        verbose_name_plural = 'Notas Fiscais de Entrada'
        ordering = ['-data_entrada', '-numero']
        unique_together = [['loja', 'chave_acesso']]
        indexes = [
            models.Index(fields=['loja', '-data_entrada']),
            models.Index(fields=['fornecedor', '-data_entrada']),
            models.Index(fields=['chave_acesso']),
        ]
    
    def __str__(self):
        return f"NF-e Entrada {self.numero}/{self.serie} - {self.fornecedor.razao_social}"


class ItemNotaFiscalEntrada(BaseModel):
    """
    Item de uma Nota Fiscal de Entrada.

    Status: NAO_VINCULADO, AGUARDANDO_CONFIRMACAO, VINCULADO, ESTOQUE_ENTRADO
    """
    STATUS_CHOICES = [
        ('NAO_VINCULADO', 'Não vinculado'),
        ('AGUARDANDO_CONFIRMACAO', 'Aguardando confirmação'),
        ('VINCULADO', 'Vinculado'),
        ('ESTOQUE_ENTRADO', 'Estoque entrado'),
    ]

    nota_fiscal = models.ForeignKey(
        NotaFiscalEntrada,
        on_delete=models.CASCADE,
        related_name='itens',
        verbose_name='Nota Fiscal',
    )
    produto = models.ForeignKey(
        Produto,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='itens_nota_entrada',
        verbose_name='Produto',
    )
    numero_item = models.IntegerField('Número do Item')
    codigo_produto_fornecedor = models.CharField('Código Produto Fornecedor', max_length=60, blank=True)
    codigo_barras = models.CharField('Código de Barras (EAN)', max_length=50, blank=True)
    ncm = models.CharField('NCM', max_length=10, blank=True)
    descricao = models.CharField('Descrição', max_length=255)
    quantidade = models.DecimalField(
        'Quantidade',
        max_digits=10,
        decimal_places=3,
        validators=[MinValueValidator(Decimal('0.001'))],
    )
    unidade_comercial = models.CharField('Unidade Comercial', max_length=10, default='UN')
    preco_unitario = models.DecimalField(
        'Preço Unitário',
        max_digits=12,
        decimal_places=4,
        validators=[MinValueValidator(Decimal('0.0001'))],
    )
    valor_total = models.DecimalField(
        'Valor Total',
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
    )
    local_estoque = models.ForeignKey(
        'estoque.LocalEstoque',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='itens_nota_entrada',
        verbose_name='Local de Estoque (override)',
        help_text='Se preenchido, sobrescreve o local padrão da nota',
    )
    status = models.CharField(
        'Status',
        max_length=25,
        choices=STATUS_CHOICES,
        default='NAO_VINCULADO',
    )
    produto_sugerido = models.ForeignKey(
        Produto,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='itens_nota_entrada_sugestao',
        verbose_name='Produto Sugerido (fuzzy match)',
    )

    class Meta:
        verbose_name = 'Item da Nota Fiscal de Entrada'
        verbose_name_plural = 'Itens da Nota Fiscal de Entrada'
        ordering = ['nota_fiscal', 'numero_item']
        unique_together = [['nota_fiscal', 'numero_item']]

    def __str__(self):
        return f"Item {self.numero_item} - {self.descricao[:50]}"


class HistoricoEntradaEstoque(models.Model):
    """
    Log de cada execução de dar_entrada_estoque_nota.
    Permite rastrear múltiplas execuções na mesma nota.
    """
    MOTIVO_PARCIAL_CHOICES = [
        ('PARCIAL_SEM_VINCULO', 'Parcial - itens sem vínculo'),
        ('PARCIAL_COM_ERRO', 'Parcial - erro técnico em algum item'),
    ]

    nota_fiscal = models.ForeignKey(
        NotaFiscalEntrada,
        on_delete=models.CASCADE,
        related_name='historico_entrada_estoque',
        verbose_name='Nota Fiscal',
        db_index=True,
    )
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='historicos_entrada_estoque',
        verbose_name='Usuário',
    )
    data_processamento = models.DateTimeField('Data do Processamento', auto_now_add=True)
    itens_processados = models.PositiveIntegerField('Itens Processados', default=0)
    motivo_parcial = models.CharField(
        'Motivo Parcial',
        max_length=25,
        choices=MOTIVO_PARCIAL_CHOICES,
        null=True,
        blank=True,
    )
    erros = models.JSONField(
        'Erros',
        default=list,
        blank=True,
        help_text='Lista de mensagens de erro por item',
    )

    class Meta:
        verbose_name = 'Histórico de Entrada em Estoque'
        verbose_name_plural = 'Históricos de Entrada em Estoque'
        ordering = ['-data_processamento']
        indexes = [
            models.Index(fields=['nota_fiscal', '-data_processamento']),
        ]

    def __str__(self):
        return f"Entrada {self.nota_fiscal.numero}/{self.nota_fiscal.serie} - {self.data_processamento}"


class AlertaNotaFiscal(BaseModel):
    """
    Alerta de NF-e detectada via API SEFAZ-BA (notas emitidas no CNPJ da empresa).

    Quando a SEFAZ-BA retorna notas onde nosso CNPJ é destinatário,
    criamos alertas para o usuário importar ou registrar manualmente.
    """
    TIPO_CHOICES = [
        ('ENTRADA', 'Nota de Entrada (destinatário)'),
        ('SAIDA', 'Nota de Saída (emitente)'),
    ]
    STATUS_CHOICES = [
        ('PENDENTE', 'Pendente'),
        ('IMPORTADA', 'Importada no sistema'),
        ('IGNORADA', 'Ignorada'),
    ]

    loja = models.ForeignKey(
        Loja,
        on_delete=models.CASCADE,
        related_name='alertas_nota_fiscal',
        verbose_name='Loja',
    )
    tipo = models.CharField('Tipo', max_length=10, choices=TIPO_CHOICES, default='ENTRADA')
    status = models.CharField('Status', max_length=20, choices=STATUS_CHOICES, default='PENDENTE')

    # Dados da nota (da SEFAZ)
    chave_acesso = models.CharField('Chave de Acesso', max_length=44, db_index=True)
    numero = models.IntegerField('Número')
    serie = models.CharField('Série', max_length=3)
    valor_total = models.DecimalField(
        'Valor Total',
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
    )
    data_emissao = models.DateField('Data de Emissão', null=True, blank=True)
    cnpj_emitente = models.CharField('CNPJ Emitente', max_length=20, blank=True)
    razao_social_emitente = models.CharField('Razão Social Emitente', max_length=255, blank=True)

    # Vinculação após importação
    nota_fiscal_entrada = models.ForeignKey(
        NotaFiscalEntrada,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='alertas',
        verbose_name='Nota Fiscal Importada',
    )

    data_consulta_sefaz = models.DateTimeField('Data da Consulta SEFAZ', auto_now_add=True)
    mensagem = models.TextField('Mensagem', blank=True)

    class Meta:
        verbose_name = 'Alerta de Nota Fiscal'
        verbose_name_plural = 'Alertas de Notas Fiscais'
        ordering = ['-data_consulta_sefaz']
        unique_together = [['loja', 'chave_acesso']]
        indexes = [
            models.Index(fields=['loja', 'status']),
            models.Index(fields=['chave_acesso']),
        ]

    def __str__(self):
        return f"Alerta NF-e {self.numero}/{self.serie} - {self.chave_acesso[:10]}..."

