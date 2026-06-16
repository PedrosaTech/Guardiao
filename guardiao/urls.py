"""
URL configuration for guardiao project.

TODO: Futuramente a API será versionada (v1, v2, etc.)
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.http import HttpResponse
from rest_framework.routers import DefaultRouter

# Importar viewsets
from core.views import EmpresaViewSet, LojaViewSet
from pessoas.views import ClienteViewSet, FornecedorViewSet
from produtos.views import CategoriaProdutoViewSet, ProdutoViewSet
from estoque.views import LocalEstoqueViewSet, EstoqueAtualViewSet, MovimentoEstoqueViewSet
from vendas.views import CondicaoPagamentoViewSet, PedidoVendaViewSet
from pdv.views_api import (
    CaixaSessaoViewSet,
    PagamentoViewSet,
    buscar_produtos_pdv,
    buscar_pedido_tablet,
    efetivar_pedido_tablet_view,
    verificar_caixa_aberto,
)
from pdv_movel.api.viewsets import PedidosPDVViewSet as PDVMovelPedidosViewSet
from crm.views import LeadViewSet, InteracaoCRMViewSet
from eventos.views import EventoVendaViewSet
from orcamentos.views import OrcamentoVendaViewSet, ItemOrcamentoVendaViewSet
from core.views import dashboard


def service_worker(request):
    """Retorna um service worker vazio para evitar erros 404."""
    response = HttpResponse(
        "// Service Worker vazio\nself.addEventListener('install', () => {});\nself.addEventListener('activate', () => {});",
        content_type='application/javascript'
    )
    return response


# Router para API REST
router = DefaultRouter()
router.register(r'empresas', EmpresaViewSet, basename='empresa')
router.register(r'lojas', LojaViewSet, basename='loja')
router.register(r'clientes', ClienteViewSet, basename='cliente')
router.register(r'fornecedores', FornecedorViewSet, basename='fornecedor')
router.register(r'categorias-produto', CategoriaProdutoViewSet, basename='categoria-produto')
router.register(r'produtos', ProdutoViewSet, basename='produto')
router.register(r'locais-estoque', LocalEstoqueViewSet, basename='local-estoque')
router.register(r'estoque-atual', EstoqueAtualViewSet, basename='estoque-atual')
router.register(r'movimentos-estoque', MovimentoEstoqueViewSet, basename='movimento-estoque')
router.register(r'condicoes-pagamento', CondicaoPagamentoViewSet, basename='condicao-pagamento')
router.register(r'pedidos-venda', PedidoVendaViewSet, basename='pedido-venda')
router.register(r'caixas-sessao', CaixaSessaoViewSet, basename='caixa-sessao')
router.register(r'pagamentos', PagamentoViewSet, basename='pagamento')
router.register(r'leads', LeadViewSet, basename='lead')
router.register(r'interacoes-crm', InteracaoCRMViewSet, basename='interacao-crm')
router.register(r'eventos', EventoVendaViewSet, basename='evento')
router.register(r'orcamentos', OrcamentoVendaViewSet, basename='orcamento')
router.register(r'itens-orcamento', ItemOrcamentoVendaViewSet, basename='item-orcamento')

urlpatterns = [
    path('', dashboard, name='dashboard'),
    path('service-worker.js', service_worker, name='service-worker'),
    path('admin/', admin.site.urls),
    path('api/v1/', include(router.urls)),
    # TODO: Adicionar rotas de autenticação da API
    path('api/v1/auth/', include('rest_framework.urls')),
    path('api/v1/pdv/produtos/', buscar_produtos_pdv, name='api-pdv-produtos'),
    path('pdv/api/buscar-pedido-tablet/', buscar_pedido_tablet),
    path('pdv/api/efetivar-pedido-tablet/', efetivar_pedido_tablet_view),
    path('pdv/api/verificar-caixa/', verificar_caixa_aberto),
    path('pdv/', include('pdv.urls')),
    path(
        'pdv-movel/api/pedidos/<int:pk>/adicionar_item/',
        PDVMovelPedidosViewSet.as_view(actions={'post': 'adicionar_item'}),
    ),
    path('eventos/', include('eventos.urls')),
    path('fiscal/', include('fiscal.urls')),
    path('produtos/', include('produtos.urls')),
    path('estoque/', include('estoque.urls')),
    path('pessoas/', include('pessoas.urls')),
    path('orcamentos/', include('orcamentos.urls')),
    path('vendas/', include('vendas.urls')),
    path('financeiro/', include('financeiro.urls')),
    path('pdv-movel/', include('pdv_movel.urls')),
    path('cadastros/', include('core.urls')),
]

# Servir arquivos de mídia em desenvolvimento
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)

handler403 = 'core.views.handler403'

