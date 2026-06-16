"""
Testes do app produtos.
"""
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
import unittest

from django.db import connection
from django.test import TestCase

from core.models import Empresa, Loja
from produtos.models import (
    CategoriaProduto,
    Produto,
    ProdutoParametrosEmpresa,
    SequenciaCodigoInterno,
)


def _produto_defaults(categoria, indice):
    return dict(
        categoria=categoria,
        descricao=f'Produto concorrente {indice}',
        classe_risco='OUTRA',
        ncm='36041000',
    )


def _ensure_parametros(produto, empresa, preco=Decimal('10.00')):
    ProdutoParametrosEmpresa.objects.get_or_create(
        empresa=empresa,
        produto=produto,
        defaults={
            'preco_venda': preco,
            'cfop_venda_dentro_uf': '5102',
            'csosn_cst': '102',
        },
    )


class TestCodigoInternoRaceCondition(TestCase):
    """Garante unicidade de codigo_interno sob saves concorrentes (sequência global)."""

    def setUp(self):
        self.empresa = Empresa.objects.create(
            nome_fantasia='Empresa Teste Seq',
            razao_social='Empresa Teste Seq LTDA',
            cnpj='12345678000199',
        )
        Loja.objects.create(empresa=self.empresa, nome='Loja 1')
        self.categoria = CategoriaProduto.objects.create(
            nome='Cat Seq',
        )

    @unittest.skipUnless(
        connection.vendor == 'postgresql',
        'SQLite bloqueia escrita concorrente em threads; use PostgreSQL para validar paralelismo real.',
    )
    def test_codigos_unicos_em_saves_concorrentes(self):
        def criar_produto(i):
            p = Produto.objects.create(**_produto_defaults(self.categoria, i))
            _ensure_parametros(p, self.empresa)
            return p

        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(criar_produto, i) for i in range(10)]
            resultados = [f.result() for f in futures]

        codigos = [p.codigo_interno for p in resultados]
        self.assertEqual(len(codigos), len(set(codigos)), 'Códigos duplicados detectados!')

        seq = SequenciaCodigoInterno.objects.get(empresa__isnull=True)
        self.assertEqual(seq.ultimo_numero, 10)

    def test_dez_produtos_sequenciais_codigos_unicos(self):
        """Roda em SQLite e Postgres; garante sequência e unicidade em série."""
        resultados = []
        for i in range(10):
            p = Produto.objects.create(**_produto_defaults(self.categoria, i))
            _ensure_parametros(p, self.empresa)
            resultados.append(p)
        codigos = [p.codigo_interno for p in resultados]
        self.assertEqual(len(codigos), len(set(codigos)))
        seq = SequenciaCodigoInterno.objects.get(empresa__isnull=True)
        self.assertEqual(seq.ultimo_numero, 10)

    def test_sequencia_incrementa_formato_prod(self):
        p1 = Produto.objects.create(**_produto_defaults(self.categoria, 1))
        _ensure_parametros(p1, self.empresa)
        p2 = Produto.objects.create(**_produto_defaults(self.categoria, 2))
        _ensure_parametros(p2, self.empresa)
        self.assertEqual(p1.codigo_interno, 'PROD-0001')
        self.assertEqual(p2.codigo_interno, 'PROD-0002')


class CatalogoGlobalProdutoTests(TestCase):
    def setUp(self):
        self.empresa = Empresa.objects.create(
            nome_fantasia='E1',
            razao_social='E1 LTDA',
            cnpj='11111111000191',
        )
        self.categoria = CategoriaProduto.objects.create(nome='Cat')
        self.produto = Produto.objects.create(
            categoria=self.categoria,
            descricao='P1',
            classe_risco='OUTRA',
            ncm='36041000',
        )
        ProdutoParametrosEmpresa.objects.create(
            empresa=self.empresa,
            produto=self.produto,
            preco_venda=Decimal('15.00'),
            cfop_venda_dentro_uf='5102',
            csosn_cst='102',
        )

    def test_produto_sem_empresa(self):
        """Produto não tem mais FK empresa"""
        self.assertFalse(hasattr(Produto, 'empresa_id'))

    def test_parametros_por_empresa_criados(self):
        """ProdutoParametrosEmpresa existe para o produto"""
        self.assertTrue(
            ProdutoParametrosEmpresa.objects.filter(
                produto=self.produto,
                empresa=self.empresa,
            ).exists()
        )

    def test_busca_por_codigo_filtra_empresa(self):
        """buscar_produto_por_codigo só retorna produtos ativos na empresa"""
        from produtos.utils import buscar_produto_por_codigo
        self.produto.codigo_barras = '7891000100003'
        self.produto.save(update_fields=['codigo_barras'])
        produto, _, _ = buscar_produto_por_codigo(
            self.produto.codigo_barras,
            empresa=self.empresa,
        )
        self.assertEqual(produto, self.produto)
