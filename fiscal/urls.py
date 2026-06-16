"""
URLs do módulo fiscal.
"""
from django.urls import path
from . import views
from . import config_loja_views

app_name = 'fiscal'

urlpatterns = [
    # Configuração Fiscal de Loja (ADMINISTRADOR)
    path('configuracao-fiscal/', config_loja_views.lista_config_fiscal, name='lista_config_fiscal'),
    path('configuracao-fiscal/nova/', config_loja_views.criar_config_fiscal, name='criar_config_fiscal'),
    path('configuracao-fiscal/<int:pk>/editar/', config_loja_views.editar_config_fiscal, name='editar_config_fiscal'),
    path('loja/<int:loja_id>/testar-sefaz/', views.testar_status_sefaz, name='testar-status-sefaz'),

    # Notas Fiscais de Saída
    path('notas-saida/', views.lista_notas_saida, name='lista_notas_saida'),
    path('notas-saida/detalhes/<int:nota_id>/', views.detalhes_nota_saida, name='detalhes_nota_saida'),
    path('nota/<int:nota_id>/gerar-xml/', views.gerar_xml_nota, name='gerar-xml-nota'),
    path('nota/<int:nota_id>/autorizar/', views.autorizar_nota, name='autorizar-nota'),
    path('nota/<int:nota_id>/cancelar/', views.cancelar_nota, name='cancelar-nota'),
    
    # Notas Fiscais de Entrada
    path('notas-entrada/', views.lista_notas_entrada, name='lista_notas_entrada'),
    path('notas-entrada/criar/', views.criar_nota_entrada, name='criar_nota_entrada'),
    path('notas-entrada/importar-xml/', views.importar_nota_entrada_xml, name='importar_nota_entrada_xml'),
    path('notas-entrada/importar-xml/confirmar/', views.importar_nota_entrada_confirmar, name='importar_nota_entrada_confirmar'),
    path('notas-entrada/detalhes/<int:nota_id>/', views.detalhes_nota_entrada, name='detalhes_nota_entrada'),
    path('notas-entrada/detalhes/<int:nota_id>/dar-entrada-estoque/', views.dar_entrada_estoque_nota_view, name='dar_entrada_estoque_nota'),
    
    # Alertas SEFAZ-BA
    path('alertas-sefaz/', views.lista_alertas_sefaz, name='lista_alertas_sefaz'),
    
    # PDF
    path('nfe/<int:nota_id>/pdf/', views.imprimir_nfe_pdf, name='imprimir_nfe_pdf'),

    # NFC-e
    path('nfce/', views.lista_nfce, name='lista_nfce'),
    path('nfce/nova/', views.criar_nfce, name='criar_nfce'),
    path('nfce/<int:nota_id>/', views.detalhes_nfce, name='detalhes_nfce'),
    path('nfce/<int:nota_id>/autorizar/', views.autorizar_nfce_view, name='autorizar_nfce'),
    path('nfce/<int:nota_id>/cancelar/', views.cancelar_nfce_view, name='cancelar_nfce'),
    path('nfce/<int:nota_id>/danfe/', views.imprimir_danfe_nfce, name='danfe_nfce'),

    # NFS-e
    path('nfse/', views.lista_nfse, name='lista_nfse'),
    path('nfse/nova/', views.criar_nfse, name='criar_nfse'),
    path('nfse/<int:nota_id>/', views.detalhes_nfse, name='detalhes_nfse'),
    path('nfse/<int:nota_id>/emitir/', views.emitir_nfse_view, name='emitir_nfse'),
    path('nfse/<int:nota_id>/cancelar/', views.cancelar_nfse_view, name='cancelar_nfse'),
    path('nfse/<int:nota_id>/pdf/', views.imprimir_nfse_pdf, name='imprimir_nfse_pdf'),
]

