from django.contrib import admin

from .models import CategoriaCafe, Comanda, ItemCardapio, ItemComanda


class ItemComandaInline(admin.TabularInline):
    model = ItemComanda
    extra = 0


class ItemCardapioInline(admin.TabularInline):
    model = ItemCardapio
    extra = 0


@admin.register(CategoriaCafe)
class CategoriaCafeAdmin(admin.ModelAdmin):
    list_display = ('nome', 'icone', 'ordem', 'is_active')
    list_editable = ('ordem',)
    inlines = [ItemCardapioInline]


@admin.register(ItemCardapio)
class ItemCardapioAdmin(admin.ModelAdmin):
    list_display = ('nome', 'categoria', 'preco', 'disponibilidade', 'destaque', 'is_active')
    list_filter = ('categoria', 'disponibilidade', 'vegano', 'sem_gluten')
    search_fields = ('nome',)


@admin.register(Comanda)
class ComandaAdmin(admin.ModelAdmin):
    list_display = ('numero', 'nome_cliente', 'loja', 'status', 'valor_total', 'created_at')
    list_filter = ('status', 'loja')
    search_fields = ('nome_cliente', 'numero')
    inlines = [ItemComandaInline]
