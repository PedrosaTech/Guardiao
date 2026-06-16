"""
Admin para modelos de produtos.
"""
from django.contrib import admin

from .models import CategoriaProduto, CodigoBarrasAlternativo, Produto, ProdutoParametrosEmpresa


class CodigoBarrasAlternativoInline(admin.TabularInline):
    """Inline para gerenciar códigos alternativos no produto."""
    model = CodigoBarrasAlternativo
    extra = 1
    fields = ['codigo_barras', 'descricao', 'multiplicador', 'is_active']
    verbose_name = 'Código Alternativo'
    verbose_name_plural = 'Códigos Alternativos'


class ProdutoParametrosEmpresaInline(admin.TabularInline):
    model = ProdutoParametrosEmpresa
    extra = 0
    fields = [
        'empresa',
        'ativo_nessa_empresa',
        'preco_venda',
        'cfop_venda_dentro_uf',
        'csosn_cst',
        'aliquota_icms',
    ]
    autocomplete_fields = ['empresa']


@admin.register(CategoriaProduto)
class CategoriaProdutoAdmin(admin.ModelAdmin):
    list_display = ['nome', 'categoria_pai', 'is_active']
    list_filter = ['is_active', 'created_at']
    search_fields = ['nome', 'descricao']
    readonly_fields = ['created_at', 'updated_at', 'created_by', 'updated_by']
    autocomplete_fields = ['categoria_pai']


@admin.register(Produto)
class ProdutoAdmin(admin.ModelAdmin):
    list_display = ['codigo_interno', 'descricao', 'categoria', 'classe_risco', 'ncm', 'is_active']
    list_filter = ['categoria', 'classe_risco', 'possui_restricao_exercito', 'is_active', 'created_at']
    search_fields = ['codigo_interno', 'codigo_barras', 'descricao', 'ncm']
    readonly_fields = ['codigo_interno', 'created_at', 'updated_at', 'created_by', 'updated_by']
    inlines = [ProdutoParametrosEmpresaInline, CodigoBarrasAlternativoInline]

    fieldsets = (
        ('Informações Básicas', {
            'fields': ('categoria', 'codigo_interno', 'codigo_barras', 'descricao'),
            'description': '⚠️ O código interno é gerado automaticamente pelo sistema ao salvar (formato: PROD-0001, PROD-0002, etc.) se deixado em branco na primeira gravação.',
        }),
        ('Características Adicionais', {
            'fields': (
                'classe_risco', 'subclasse_risco', 'possui_restricao_exercito',
                'numero_certificado_exercito', 'numero_lote', 'validade', 'condicoes_armazenamento'
            )
        }),
        ('Dados Fiscais Globais', {
            'fields': ('ncm', 'cest', 'unidade_comercial', 'origem'),
        }),
        ('Outros', {
            'fields': ('observacoes',),
        }),
        ('Controle', {
            'fields': ('is_active', 'created_at', 'updated_at', 'created_by', 'updated_by')
        }),
    )


@admin.register(ProdutoParametrosEmpresa)
class ProdutoParametrosEmpresaAdmin(admin.ModelAdmin):
    list_display = [
        'produto',
        'empresa',
        'preco_venda',
        'ativo_nessa_empresa',
        'cfop_venda_dentro_uf',
        'csosn_cst',
        'is_active',
    ]
    list_filter = ['empresa', 'ativo_nessa_empresa', 'is_active']
    search_fields = ['produto__codigo_interno', 'produto__descricao', 'empresa__nome_fantasia']
    autocomplete_fields = ['empresa', 'produto']
    readonly_fields = ['created_at', 'updated_at', 'created_by', 'updated_by']


@admin.register(CodigoBarrasAlternativo)
class CodigoBarrasAlternativoAdmin(admin.ModelAdmin):
    """Admin separado para códigos alternativos."""
    list_display = [
        'codigo_barras',
        'produto_codigo',
        'produto_descricao',
        'descricao',
        'multiplicador',
        'is_active',
    ]
    list_filter = ['is_active']
    search_fields = [
        'codigo_barras',
        'produto__codigo_interno',
        'produto__descricao',
        'descricao',
    ]
    autocomplete_fields = ['produto']
    readonly_fields = ['created_at', 'updated_at', 'created_by', 'updated_by']

    def produto_codigo(self, obj):
        return obj.produto.codigo_interno

    produto_codigo.short_description = 'Código Produto'
    produto_codigo.admin_order_field = 'produto__codigo_interno'

    def produto_descricao(self, obj):
        return obj.produto.descricao

    produto_descricao.short_description = 'Descrição Produto'
    produto_descricao.admin_order_field = 'produto__descricao'
