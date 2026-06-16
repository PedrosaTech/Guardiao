"""
Admin para modelos do PDV.
"""
from django.contrib import admin
from .models import CaixaSessao, Pagamento


@admin.register(CaixaSessao)
class CaixaSessaoAdmin(admin.ModelAdmin):
    list_display = ['loja', 'usuario_abertura', 'data_hora_abertura', 'saldo_inicial', 'status', 'saldo_final', 'data_hora_fechamento']
    list_filter = ['status', 'loja', 'data_hora_abertura']
    search_fields = ['loja__nome', 'usuario_abertura__username']
    readonly_fields = ['data_hora_abertura', 'created_at', 'updated_at', 'created_by', 'updated_by']
    date_hierarchy = 'data_hora_abertura'


@admin.register(Pagamento)
class PagamentoAdmin(admin.ModelAdmin):
    list_display = ['pedido', 'caixa_sessao', 'tipo', 'valor', 'created_at']
    list_filter = ['tipo', 'caixa_sessao__loja', 'created_at']
    search_fields = ['pedido__id', 'caixa_sessao__loja__nome']
    readonly_fields = ['created_at', 'updated_at', 'created_by', 'updated_by']
