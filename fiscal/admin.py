"""
Admin para modelos fiscais.
"""
from django.contrib import admin
from .forms import ConfiguracaoFiscalLojaAdminForm
from .models import (
    ConfiguracaoFiscalLoja,
    NotaFiscalSaida,
    NotaFiscalEntrada,
    ItemNotaFiscalEntrada,
    HistoricoEntradaEstoque,
    AlertaNotaFiscal,
    NotaFiscalConsumidor,
    ItemNotaFiscalConsumidor,
    NotaFiscalServico,
)


@admin.register(ConfiguracaoFiscalLoja)
class ConfiguracaoFiscalLojaAdmin(admin.ModelAdmin):
    form = ConfiguracaoFiscalLojaAdminForm
    list_display = ['loja', 'cnpj', 'inscricao_estadual', 'regime_tributario', 'usar_reforma_2026', 'ambiente', 'is_active']
    list_filter = ['ambiente', 'usar_reforma_2026', 'is_active']
    search_fields = ['loja__nome', 'cnpj', 'inscricao_estadual']
    readonly_fields = ['created_at', 'updated_at', 'created_by', 'updated_by']
    
    fieldsets = (
        ('Loja', {
            'fields': ('loja',)
        }),
        ('Dados Fiscais', {
            'fields': ('cnpj', 'inscricao_estadual', 'regime_tributario')
        }),
        ('Certificado Digital', {
            'fields': ('certificado_arquivo', 'senha_certificado')
        }),
        ('Configurações de Emissão', {
            'fields': (
                'ambiente', 'serie_nfe', 'serie_nfce', 'proximo_numero_nfe', 'proximo_numero_nfce',
                'csc_id', 'csc_token',
            )
        }),
        ('NFS-e Nacional', {
            'fields': ('inscricao_municipal', 'codigo_cnae', 'serie_rps', 'proximo_numero_rps'),
        }),
        ('Reforma Tributária 2026', {
            'fields': ('usar_reforma_2026', 'aliquota_ibs_padrao_2026', 'aliquota_cbs_padrao_2026'),
            'description': '⚠️ Ative apenas quando estiver pronto para usar CBS/IBS. Sistema funciona normalmente com reforma desligada.'
        }),
        ('Controle', {
            'fields': ('is_active', 'created_at', 'updated_at', 'created_by', 'updated_by')
        }),
    )


@admin.register(NotaFiscalSaida)
class NotaFiscalSaidaAdmin(admin.ModelAdmin):
    list_display = ['numero', 'serie', 'tipo_documento', 'loja', 'cliente', 'evento', 'valor_total', 'status', 'data_emissao']
    list_filter = ['tipo_documento', 'status', 'loja', 'evento', 'data_emissao']
    search_fields = ['numero', 'chave_acesso', 'cliente__nome_razao_social']
    readonly_fields = ['created_at', 'updated_at', 'created_by', 'updated_by']
    date_hierarchy = 'data_emissao'
    
    def get_urls(self):
        from django.urls import path
        urls = super().get_urls()
        custom_urls = [
            path(
                '<int:nota_id>/imprimir-pdf/',
                self.admin_site.admin_view(self.imprimir_pdf_view),
                name='fiscal_notafiscalsaida_imprimir_pdf',
            ),
        ]
        return custom_urls + urls
    
    def imprimir_pdf_view(self, request, nota_id):
        """View para imprimir PDF da NF-e."""
        from django.shortcuts import redirect
        from django.urls import reverse
        return redirect(reverse('fiscal:imprimir_nfe_pdf', args=[nota_id]))
    
    def change_view(self, request, object_id, form_url='', extra_context=None):
        extra_context = extra_context or {}
        extra_context['show_imprimir_button'] = True
        return super().change_view(request, object_id, form_url, extra_context)
    
    fieldsets = (
        ('Informações Básicas', {
            'fields': ('loja', 'cliente', 'pedido_venda', 'evento', 'tipo_documento')
        }),
        ('Dados da Nota', {
            'fields': ('numero', 'serie', 'chave_acesso', 'valor_total', 'status', 'data_emissao')
        }),
        ('Cancelamento', {
            'fields': ('motivo_cancelamento',)
        }),
        ('XML', {
            'fields': ('xml_arquivo',)
        }),
        ('Controle', {
            'fields': ('is_active', 'created_at', 'updated_at', 'created_by', 'updated_by')
        }),
    )


class ItemNotaFiscalEntradaInline(admin.TabularInline):
    model = ItemNotaFiscalEntrada
    extra = 0
    fields = ['numero_item', 'descricao', 'produto', 'quantidade', 'preco_unitario', 'valor_total', 'status']
    readonly_fields = ['numero_item', 'descricao', 'valor_total']


@admin.register(NotaFiscalEntrada)
class NotaFiscalEntradaAdmin(admin.ModelAdmin):
    list_display = ['numero', 'serie', 'loja', 'fornecedor', 'valor_total', 'status', 'data_emissao', 'data_entrada']
    list_filter = ['status', 'loja', 'data_emissao', 'data_entrada']
    search_fields = ['numero', 'chave_acesso', 'fornecedor__razao_social']
    readonly_fields = ['created_at', 'updated_at', 'created_by', 'updated_by']
    date_hierarchy = 'data_entrada'
    inlines = [ItemNotaFiscalEntradaInline]


@admin.register(HistoricoEntradaEstoque)
class HistoricoEntradaEstoqueAdmin(admin.ModelAdmin):
    list_display = ['nota_fiscal', 'usuario', 'data_processamento', 'itens_processados', 'motivo_parcial']
    list_filter = ['motivo_parcial']
    search_fields = ['nota_fiscal__numero', 'nota_fiscal__chave_acesso']
    readonly_fields = ['data_processamento']


@admin.register(AlertaNotaFiscal)
class AlertaNotaFiscalAdmin(admin.ModelAdmin):
    list_display = ['numero', 'serie', 'loja', 'razao_social_emitente', 'valor_total', 'status', 'data_consulta_sefaz']
    list_filter = ['status', 'tipo', 'loja']
    search_fields = ['chave_acesso', 'razao_social_emitente', 'cnpj_emitente']
    readonly_fields = ['data_consulta_sefaz', 'created_at', 'updated_at']


class ItemNotaFiscalConsumidorInline(admin.TabularInline):
    model = ItemNotaFiscalConsumidor
    extra = 0
    fields = ['produto', 'descricao', 'quantidade', 'valor_unitario', 'valor_total', 'cfop', 'ncm']


@admin.register(NotaFiscalConsumidor)
class NotaFiscalConsumidorAdmin(admin.ModelAdmin):
    list_display = ['numero', 'serie', 'loja', 'status', 'valor_total', 'modalidade', 'created_at']
    list_filter = ['status', 'ambiente', 'modalidade', 'loja']
    search_fields = ['numero', 'chave_acesso', 'nome_consumidor', 'cpf_consumidor']
    readonly_fields = ['created_at', 'updated_at', 'created_by', 'updated_by']
    inlines = [ItemNotaFiscalConsumidorInline]


@admin.register(NotaFiscalServico)
class NotaFiscalServicoAdmin(admin.ModelAdmin):
    list_display = ['numero_rps', 'numero', 'loja', 'nome_tomador', 'status', 'valor_servico', 'created_at']
    list_filter = ['status', 'loja']
    search_fields = ['numero', 'numero_rps', 'nome_tomador', 'cpf_cnpj_tomador']
    readonly_fields = ['created_at', 'updated_at', 'created_by', 'updated_by']

