from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('cafe', '0002_adicionar_cardapio'),
    ]

    operations = [
        migrations.AddField(
            model_name='itemcardapio',
            name='icone',
            field=models.CharField(
                blank=True,
                help_text='Deixe vazio para usar o ícone da categoria',
                max_length=10,
                verbose_name='Ícone (emoji)',
            ),
        ),
    ]
