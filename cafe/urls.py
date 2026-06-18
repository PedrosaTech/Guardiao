from django.urls import path

from . import views

app_name = 'cafe'

urlpatterns = [
    path('', views.lista_comandas, name='lista'),
    path('nova/', views.nova_comanda, name='nova'),
    # Cardápio (antes das rotas com pk numérico)
    path('cardapio/', views.lista_cardapio, name='cardapio'),
    path('cardapio/publico/', views.cardapio_publico, name='cardapio_publico'),
    path('cardapio/categoria/nova/', views.nova_categoria, name='nova_categoria'),
    path('cardapio/categoria/<int:pk>/editar/', views.editar_categoria, name='editar_categoria'),
    path('cardapio/item/novo/', views.novo_item_cardapio, name='novo_item'),
    path('cardapio/item/<int:pk>/editar/', views.editar_item_cardapio, name='editar_item'),
    path('cardapio/item/<int:pk>/disponibilidade/', views.toggle_disponibilidade, name='toggle_disponibilidade'),
    path('<int:pk>/', views.comanda_detalhe, name='detalhe'),
    path('<int:pk>/adicionar/', views.adicionar_item, name='adicionar_item'),
    path('<int:pk>/adicionar/rapido/', views.adicionar_item_rapido, name='adicionar_item_rapido'),
    path('<int:pk>/fechar/', views.fechar_conta, name='fechar'),
    path('<int:pk>/recibo/', views.recibo, name='recibo'),
    path('item/<int:item_pk>/cancelar/', views.cancelar_item, name='cancelar_item'),
    path('api/buscar-produtos/', views.buscar_produtos, name='buscar_produtos'),
]
