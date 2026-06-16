"""
Reserva atômica de número de documento fiscal (NF-e / NFC-e).

Usa select_for_update dentro de transaction.atomic().
Não chame select_for_update fora deste módulo sem transação.
"""
from django.db import transaction


def reservar_numero_nfe(loja):
    """
    Reserva o próximo número de NF-e da loja e incrementa o contador.

    Returns:
        tuple[int, str]: (numero, serie)

    Raises:
        ConfiguracaoFiscalLoja.DoesNotExist: loja sem configuração fiscal ativa.
    """
    from .models import ConfiguracaoFiscalLoja

    with transaction.atomic():
        config = (
            ConfiguracaoFiscalLoja.objects.select_for_update().get(
                loja=loja,
                is_active=True,
            )
        )
        numero = config.proximo_numero_nfe
        serie = config.serie_nfe
        config.proximo_numero_nfe = numero + 1
        config.save(update_fields=['proximo_numero_nfe', 'updated_at'])

    return numero, serie


def reservar_numero_nfce(loja):
    """
    Reserva o próximo número de NFC-e da loja e incrementa o contador.

    Returns:
        tuple[int, str]: (numero, serie)

    Raises:
        ConfiguracaoFiscalLoja.DoesNotExist: loja sem configuração fiscal ativa.
    """
    from .models import ConfiguracaoFiscalLoja

    with transaction.atomic():
        config = (
            ConfiguracaoFiscalLoja.objects.select_for_update().get(
                loja=loja,
                is_active=True,
            )
        )
        numero = config.proximo_numero_nfce
        serie = config.serie_nfce
        config.proximo_numero_nfce = numero + 1
        config.save(update_fields=['proximo_numero_nfce', 'updated_at'])

    return numero, serie


def reservar_numero_rps(loja):
    """
    Reserva o próximo número de RPS da loja e incrementa o contador.

    Returns:
        tuple[int, str]: (numero_rps, serie_rps)
    """
    from .models import ConfiguracaoFiscalLoja

    with transaction.atomic():
        config = (
            ConfiguracaoFiscalLoja.objects.select_for_update().get(
                loja=loja,
                is_active=True,
            )
        )
        numero = config.proximo_numero_rps
        serie = config.serie_rps
        config.proximo_numero_rps = numero + 1
        config.save(update_fields=['proximo_numero_rps', 'updated_at'])

    return numero, serie
