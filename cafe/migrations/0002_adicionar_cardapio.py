# Generated manually for cardápio do Café Al-qui-mia

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def limpar_itens_comanda(apps, schema_editor):
    """Remove itens antigos vinculados a produtos do ERP."""
    ItemComanda = apps.get_model('cafe', 'ItemComanda')
    ItemComanda.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ('cafe', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='CategoriaCafe',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Data de criação')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Data de atualização')),
                ('is_active', models.BooleanField(default=True, verbose_name='Ativo')),
                ('nome', models.CharField(max_length=50, verbose_name='Categoria')),
                ('ordem', models.PositiveIntegerField(default=0, verbose_name='Ordem de exibição')),
                ('icone', models.CharField(default='☕', max_length=10, verbose_name='Ícone (emoji)')),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='%(class)s_created', to=settings.AUTH_USER_MODEL, verbose_name='Criado por')),
                ('updated_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='%(class)s_updated', to=settings.AUTH_USER_MODEL, verbose_name='Atualizado por')),
            ],
            options={
                'verbose_name': 'Categoria do Café',
                'verbose_name_plural': 'Categorias do Café',
                'ordering': ['ordem', 'nome'],
            },
        ),
        migrations.CreateModel(
            name='ItemCardapio',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Data de criação')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Data de atualização')),
                ('is_active', models.BooleanField(default=True, verbose_name='Ativo')),
                ('nome', models.CharField(max_length=100, verbose_name='Nome do Item')),
                ('descricao', models.TextField(blank=True, verbose_name='Descrição')),
                ('ingredientes', models.TextField(blank=True, help_text='Ingredientes principais, separados por vírgula', verbose_name='Ingredientes')),
                ('preco', models.DecimalField(decimal_places=2, max_digits=8, verbose_name='Preço')),
                ('disponibilidade', models.CharField(choices=[('DISPONIVEL', 'Disponível'), ('INDISPONIVEL', 'Indisponível'), ('SAZONAL', 'Sazonal')], default='DISPONIVEL', max_length=20)),
                ('destaque', models.BooleanField(default=False, verbose_name='Destaque no cardápio')),
                ('vegano', models.BooleanField(default=False, verbose_name='Vegano')),
                ('sem_gluten', models.BooleanField(default=False, verbose_name='Sem Glúten')),
                ('ordem', models.PositiveIntegerField(default=0, verbose_name='Ordem de exibição')),
                ('tempo_preparo', models.PositiveIntegerField(default=5, verbose_name='Tempo de preparo (min)')),
                ('categoria', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='itens', to='cafe.categoriacafe')),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='%(class)s_created', to=settings.AUTH_USER_MODEL, verbose_name='Criado por')),
                ('updated_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='%(class)s_updated', to=settings.AUTH_USER_MODEL, verbose_name='Atualizado por')),
            ],
            options={
                'verbose_name': 'Item do Cardápio',
                'verbose_name_plural': 'Itens do Cardápio',
                'ordering': ['categoria__ordem', 'ordem', 'nome'],
            },
        ),
        migrations.RunPython(limpar_itens_comanda, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name='itemcomanda',
            name='produto',
        ),
        migrations.AddField(
            model_name='itemcomanda',
            name='item_cardapio',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='cafe.itemcardapio'),
            preserve_default=False,
        ),
    ]
