"""
Modelos de Produtos.
"""
from django.db import models
from django.db import transaction
from django.core.validators import MinValueValidator
from decimal import Decimal

from core.models import BaseModel


class CategoriaProduto(BaseModel):
    """
    Categoria global de produtos — compartilhada entre todas as empresas.
    """

    nome = models.CharField('Nome', max_length=100)
    descricao = models.TextField('Descrição', blank=True, null=True)
    categoria_pai = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='subcategorias',
        verbose_name='Categoria Pai',
    )

    class Meta:
        verbose_name = 'Categoria de Produto'
        verbose_name_plural = 'Categorias de Produto'
        ordering = ['nome']
        unique_together = [['categoria_pai', 'nome']]

    def __str__(self):
        if self.categoria_pai:
            return f"{self.categoria_pai.nome} > {self.nome}"
        return self.nome


class SequenciaCodigoInterno(models.Model):
    """
    Contador atômico por empresa (legado) e sequência global (empresa vazia)
    para gerar codigo_interno (PROD-NNNN) sem race condition.
    """

    empresa = models.OneToOneField(
        'core.Empresa',
        on_delete=models.CASCADE,
        related_name='sequencia_codigo_interno',
        null=True,
        blank=True,
    )
    ultimo_numero = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = 'Sequência Código Interno'
        verbose_name_plural = 'Sequências Código Interno'

    def __str__(self):
        if self.empresa_id:
            return f'{self.empresa_id}: {self.ultimo_numero}'
        return f'GLOBAL: {self.ultimo_numero}'


class Produto(BaseModel):
    """
    Produto no catálogo global (identidade + NCM/CEST, sem vínculo direto a empresa).
    """

    CLASSE_RISCO_CHOICES = [
        ('OUTRA', 'Não Aplicável'),
    ]

    categoria = models.ForeignKey(
        CategoriaProduto,
        on_delete=models.PROTECT,
        related_name='produtos',
        verbose_name='Categoria',
    )
    codigo_interno = models.CharField(
        'Código Interno', max_length=50, blank=True, null=True, editable=False, unique=True
    )
    codigo_barras = models.CharField('Código de Barras', max_length=50, blank=True, null=True)
    descricao = models.CharField('Descrição', max_length=255)

    classe_risco = models.CharField(
        'Classe de Risco',
        max_length=10,
        choices=CLASSE_RISCO_CHOICES,
        default='OUTRA',
        help_text='Classificação de risco do produto (quando aplicável)',
    )
    subclasse_risco = models.CharField('Subclasse de Risco', max_length=10, blank=True, null=True)
    possui_restricao_exercito = models.BooleanField('Possui Restrição de Exército', default=False)
    numero_certificado_exercito = models.CharField(
        'Número do Certificado do Exército', max_length=50, blank=True, null=True
    )
    numero_lote = models.CharField('Número do Lote', max_length=50, blank=True, null=True)
    validade = models.DateField('Validade', blank=True, null=True)
    condicoes_armazenamento = models.TextField('Condições de Armazenamento', blank=True, null=True)

    ncm = models.CharField('NCM', max_length=10, help_text='Ex: 3604.10.00')
    cest = models.CharField('CEST', max_length=10, blank=True, null=True, help_text='Ex: 09.001.00')

    unidade_comercial = models.CharField(
        'Unidade Comercial', max_length=10, default='UN', help_text='Ex: CX, PC, UN'
    )
    origem = models.CharField('Origem', max_length=1, default='0', help_text='TODO: Trocar por choices')

    observacoes = models.TextField('Observações', blank=True, null=True)

    class Meta:
        verbose_name = 'Produto'
        verbose_name_plural = 'Produtos'
        ordering = ['codigo_interno']
        indexes = [
            models.Index(fields=['is_active']),
            models.Index(fields=['categoria', 'is_active']),
            models.Index(fields=['classe_risco', 'is_active']),
            models.Index(fields=['codigo_barras']),
        ]

    def save(self, *args, **kwargs):
        """
        Gera código interno automaticamente se não existir (sequência global).
        Formato: PROD-0001, PROD-0002, etc.
        """
        if not self.codigo_interno:
            with transaction.atomic():
                seq, _ = SequenciaCodigoInterno.objects.select_for_update().get_or_create(
                    empresa=None,
                    defaults={'ultimo_numero': 0},
                )
                seq.ultimo_numero += 1
                seq.save(update_fields=['ultimo_numero'])
                self.codigo_interno = f'PROD-{seq.ultimo_numero:04d}'

        super().save(*args, **kwargs)

    def get_todos_codigos(self):
        codigos = [self.codigo_barras] if self.codigo_barras else []
        codigos.extend(
            self.codigos_alternativos.filter(is_active=True)
            .values_list('codigo_barras', flat=True)
        )
        return list(codigos)

    def __str__(self):
        return f"{self.codigo_interno} - {self.descricao}"


class ProdutoParametrosEmpresa(BaseModel):
    """
    Parâmetros comerciais e fiscais de um produto por empresa.
    """

    empresa = models.ForeignKey(
        'core.Empresa',
        on_delete=models.CASCADE,
        related_name='parametros_produtos',
        verbose_name='Empresa',
    )
    produto = models.ForeignKey(
        Produto,
        on_delete=models.CASCADE,
        related_name='parametros_por_empresa',
        verbose_name='Produto',
    )
    ativo_nessa_empresa = models.BooleanField(
        'Ativo nessa Empresa',
        default=True,
        help_text='Se False, produto não aparece nas operações desta empresa',
    )

    preco_venda = models.DecimalField(
        'Preço de Venda',
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
    )

    cfop_venda_dentro_uf = models.CharField(
        'CFOP Venda Dentro UF',
        max_length=4,
        help_text='Ex: 5102',
    )
    cfop_venda_fora_uf = models.CharField(
        'CFOP Venda Fora UF',
        max_length=4,
        blank=True,
        null=True,
        help_text='Ex: 6102',
    )

    csosn_cst = models.CharField('CSOSN / CST ICMS', max_length=3)
    aliquota_icms = models.DecimalField(
        'Alíquota ICMS (%)',
        max_digits=5,
        decimal_places=2,
        default=Decimal('18.00'),
    )

    icms_st_cst = models.CharField(
        'CST/CSOSN ICMS-ST',
        max_length=3,
        blank=True,
        null=True,
    )
    aliquota_icms_st = models.DecimalField(
        'Alíquota ICMS-ST (%)',
        max_digits=5,
        decimal_places=2,
        default=Decimal('0.00'),
        blank=True,
        null=True,
    )

    pis_cst = models.CharField('CST PIS', max_length=2, default='01')
    aliquota_pis = models.DecimalField(
        'Alíquota PIS (%)',
        max_digits=5,
        decimal_places=2,
        default=Decimal('1.65'),
    )

    cofins_cst = models.CharField('CST COFINS', max_length=2, default='01')
    aliquota_cofins = models.DecimalField(
        'Alíquota COFINS (%)',
        max_digits=5,
        decimal_places=2,
        default=Decimal('7.60'),
    )

    ipi_venda_cst = models.CharField(
        'CST IPI Venda',
        max_length=2,
        default='52',
    )
    aliquota_ipi_venda = models.DecimalField(
        'Alíquota IPI Venda (%)',
        max_digits=5,
        decimal_places=2,
        default=Decimal('0.00'),
    )

    ipi_compra_cst = models.CharField(
        'CST IPI Compra',
        max_length=2,
        default='02',
    )
    aliquota_ipi_compra = models.DecimalField(
        'Alíquota IPI Compra (%)',
        max_digits=5,
        decimal_places=2,
        default=Decimal('0.00'),
        blank=True,
        null=True,
    )

    cclass_trib = models.CharField(
        'Classificação Tributária',
        max_length=10,
        blank=True,
        null=True,
    )
    cst_ibs = models.CharField('CST-IBS', max_length=3, blank=True, null=True)
    cst_cbs = models.CharField('CST-CBS', max_length=3, blank=True, null=True)
    aliquota_ibs = models.DecimalField(
        'Alíquota IBS (%)',
        max_digits=5,
        decimal_places=2,
        default=Decimal('0.10'),
    )
    aliquota_cbs = models.DecimalField(
        'Alíquota CBS (%)',
        max_digits=5,
        decimal_places=2,
        default=Decimal('0.90'),
    )

    class Meta:
        verbose_name = 'Parâmetros do Produto por Empresa'
        verbose_name_plural = 'Parâmetros de Produtos por Empresa'
        unique_together = [['empresa', 'produto']]
        indexes = [
            models.Index(fields=['empresa', 'ativo_nessa_empresa']),
            models.Index(fields=['produto', 'empresa']),
        ]

    def __str__(self):
        return f"{self.produto.codigo_interno} @ {self.empresa.nome_fantasia}"


class CodigoBarrasAlternativo(BaseModel):
    """
    Códigos de barras alternativos vinculados a um produto principal.
    """

    produto = models.ForeignKey(
        Produto,
        on_delete=models.CASCADE,
        related_name='codigos_alternativos',
        verbose_name='Produto Principal',
        help_text='Produto ao qual este código alternativo está vinculado',
    )
    codigo_barras = models.CharField(
        'Código de Barras Alternativo',
        max_length=50,
        db_index=True,
        help_text='EAN/GTIN alternativo mapeado para o produto principal',
    )
    descricao = models.CharField(
        'Descrição/Motivo',
        max_length=100,
        blank=True,
        help_text='Ex: Embalagem promocional, Código fornecedor X, Caixa 12 un, etc.',
    )
    multiplicador = models.DecimalField(
        'Multiplicador',
        max_digits=10,
        decimal_places=3,
        default=Decimal('1.000'),
        validators=[MinValueValidator(Decimal('0.001'))],
        help_text='Ex: Caixa com 12 unidades = 12.000',
    )
    fornecedor = models.ForeignKey(
        'pessoas.Fornecedor',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='codigos_alternativos',
        verbose_name='Fornecedor',
        help_text='Opcional. Fornecedor deste código alternativo.',
    )

    class Meta:
        verbose_name = 'Código de Barras Alternativo'
        verbose_name_plural = 'Códigos de Barras Alternativos'
        unique_together = [['produto', 'codigo_barras']]
        ordering = ['produto', 'codigo_barras']
        indexes = [
            models.Index(fields=['codigo_barras']),
            models.Index(fields=['produto', 'is_active']),
        ]

    def __str__(self):
        parts = [f"{self.codigo_barras} → {self.produto.codigo_interno}"]
        if self.descricao:
            parts.append(f"({self.descricao})")
        if self.fornecedor:
            parts.append(f"[Forn: {self.fornecedor.razao_social}]")
        if self.multiplicador != 1:
            parts.append(f"[{self.multiplicador}x]")
        return " ".join(parts)

    def clean(self):
        from django.core.exceptions import ValidationError

        super().clean()
        if not self.codigo_barras:
            return

        self.codigo_barras = self.codigo_barras.strip()

        if not self.codigo_barras.isdigit():
            raise ValidationError({
                'codigo_barras': 'Código de barras deve conter apenas números.'
            })
        if len(self.codigo_barras) not in [8, 12, 13, 14]:
            raise ValidationError({
                'codigo_barras': 'Código de barras deve ter 8, 12, 13 ou 14 dígitos (EAN/GTIN/UPC).'
            })

        codigo_principal = (self.produto.codigo_barras or '').strip()
        if codigo_principal and self.codigo_barras == codigo_principal:
            raise ValidationError({
                'codigo_barras': 'Código alternativo não pode ser igual ao código principal do produto.'
            })

        conflito = Produto.objects.filter(
            codigo_barras=self.codigo_barras,
            is_active=True,
        ).exclude(pk=self.produto_id).exists()
        if conflito:
            raise ValidationError({
                'codigo_barras': 'Este código já é o código principal de outro produto.'
            })

        conflito_alt = CodigoBarrasAlternativo.objects.filter(
            codigo_barras=self.codigo_barras,
            is_active=True,
        ).exclude(pk=self.pk).exists()
        if conflito_alt:
            raise ValidationError({
                'codigo_barras': 'Este código já está vinculado a outro produto.'
            })
