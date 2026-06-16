from django.db import migrations


def normalizar_classe_risco(apps, schema_editor):
    Produto = apps.get_model('produtos', 'Produto')
    Produto.objects.exclude(classe_risco='OUTRA').update(classe_risco='OUTRA')


class Migration(migrations.Migration):

    dependencies = [
        ('produtos', '0011_limpar_classe_risco'),
    ]

    operations = [
        migrations.RunPython(normalizar_classe_risco, migrations.RunPython.noop),
    ]
