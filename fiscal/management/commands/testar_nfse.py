from decimal import Decimal
import json

from django.core.management.base import BaseCommand
from django.db.models import Max

from fiscal.models import ConfiguracaoFiscalLoja, NotaFiscalServico
from fiscal.numeracao import reservar_numero_rps
from fiscal.nfse_nacional import (
    calcular_valores_nfse,
    emitir_nfse,
    gerar_xml_dps,
    get_emit_url,
)


class Command(BaseCommand):
    help = 'Testa emissão de NFS-e em homologação'

    def add_arguments(self, parser):
        parser.add_argument(
            '--enviar',
            action='store_true',
            help='Envia para homologação sem pedir confirmação',
        )

    def handle(self, *args, **kwargs):
        config = ConfiguracaoFiscalLoja.objects.filter(
            ambiente='HOMOLOGACAO',
            is_active=True,
        ).select_related('loja', 'loja__empresa').first()

        if not config:
            self.stdout.write(self.style.ERROR('Nenhuma config fiscal em homologação encontrada.'))
            return

        loja = config.loja
        empresa = loja.empresa

        self.stdout.write(f'Usando loja: {loja}')
        self.stdout.write(f'CNPJ: {empresa.cnpj}')
        self.stdout.write(f'Inscrição Municipal: {config.inscricao_municipal or "—"}')
        self.stdout.write(
            f'IBGE: {loja.codigo_ibge_municipio or empresa.codigo_ibge_municipio or "2919207 (fallback)"}'
        )
        self.stdout.write(f'Cidade: {loja.cidade or empresa.cidade or "Lauro de Freitas (fallback)"}')

        max_rps = (
            NotaFiscalServico.objects.filter(loja=loja).aggregate(Max('numero_rps'))['numero_rps__max']
            or 0
        )
        if config.proximo_numero_rps <= max_rps:
            config.proximo_numero_rps = max_rps + 1
            config.save(update_fields=['proximo_numero_rps', 'updated_at'])
            self.stdout.write(
                self.style.WARNING(
                    f'Contador RPS ajustado para {config.proximo_numero_rps} (último no banco: {max_rps})'
                )
            )

        preview_numero = config.proximo_numero_rps
        preview_serie = config.serie_rps or 'RPS'

        nfse = NotaFiscalServico(
            loja=loja,
            numero_rps=preview_numero,
            serie_rps=preview_serie,
            status='RASCUNHO',
            nome_tomador='CONSUMIDOR TESTE',
            cpf_cnpj_tomador='000.000.000-00',
            codigo_servico='01.01',
            discriminacao='Serviço de teste NFS-e homologação Guardião ERP',
            municipio_prestacao=loja.codigo_ibge_municipio or empresa.codigo_ibge_municipio or '2919207',
            valor_servico=Decimal('100.00'),
            valor_deducoes=Decimal('0.00'),
            aliquota_iss=Decimal('0.05'),
            iss_retido=False,
        )

        calcular_valores_nfse(nfse)
        xml_dps = gerar_xml_dps(nfse, config).decode('utf-8')
        self.stdout.write(f'\nEndpoint: {get_emit_url(homologacao=True)}')
        self.stdout.write('\n=== XML DPS (sem assinatura) ===')
        self.stdout.write(xml_dps)

        enviar = kwargs.get('enviar')
        if not enviar:
            resposta = input('\nEnviar para SEFAZ homologação? (s/N): ')
            enviar = resposta.lower() == 's'
        if not enviar:
            self.stdout.write('Cancelado.')
            return

        numero_rps, serie_rps = reservar_numero_rps(loja)
        nfse.numero_rps = numero_rps
        nfse.serie_rps = serie_rps
        nfse.save()
        resultado = emitir_nfse(nfse, config)
        self.stdout.write('\n=== RESULTADO ===')
        self.stdout.write(json.dumps(resultado, ensure_ascii=False, indent=2, default=str))

        if resultado.get('sucesso'):
            self.stdout.write(self.style.SUCCESS(f"NFS-e {resultado['numero']} autorizada!"))
        else:
            self.stdout.write(self.style.ERROR(f"Erro: {resultado.get('erro')}"))
