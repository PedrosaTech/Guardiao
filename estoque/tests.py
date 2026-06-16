"""
Testes do app estoque.
"""
import pytest
from decimal import Decimal
from django.core.exceptions import ValidationError

from core.models import Empresa, Loja
from produtos.models import CategoriaProduto, Produto, ProdutoParametrosEmpresa

from .models import EstoqueAtual, EstoqueValorado, LocalEstoque, TransferenciaInterempresa
from .services import realizar_movimento_estoque
from .transferencia import executar_transferencia_interempresa
from .valoracao import atualizar_custo_medio, atualizar_quantidade_total


@pytest.mark.django_db
class TestMovimentacaoEstoque:
    """Testes para movimentação de estoque."""
    
    def test_movimentacao_estoque_entrada(self):
        """Testa entrada de estoque."""
        empresa = Empresa.objects.create(
            nome_fantasia='Guardião',
            razao_social='Guardião Ltda',
            cnpj='12345678000190',
        )
        loja = Loja.objects.create(
            empresa=empresa,
            nome='Loja Centro',
        )
        categoria = CategoriaProduto.objects.create(
            nome='Bombas',
        )
        produto = Produto.objects.create(
            categoria=categoria,
            codigo_interno='BOM001',
            descricao='Bomba de Festa',
            classe_risco='OUTRA',
            ncm='36041000',
            unidade_comercial='UN',
            origem='0',
        )
        ProdutoParametrosEmpresa.objects.create(
            empresa=empresa,
            produto=produto,
            preco_venda=Decimal('10.00'),
            cfop_venda_dentro_uf='5102',
            csosn_cst='102',
            aliquota_icms=Decimal('18.00'),
        )
        local = LocalEstoque.objects.create(
            loja=loja,
            nome='Depósito Principal',
        )
        
        # Realiza entrada
        movimento = realizar_movimento_estoque(
            produto=produto,
            tipo_movimento='ENTRADA',
            quantidade=Decimal('100.000'),
            local_destino=local,
        )
        
        assert movimento.id is not None
        assert movimento.tipo_movimento == 'ENTRADA'
        
        # Verifica estoque atualizado
        estoque = EstoqueAtual.objects.get(produto=produto, local_estoque=local)
        assert estoque.quantidade == Decimal('100.000')


@pytest.mark.django_db
class TestEstoqueValorado:
    """Custo médio ponderado e quantidade_total por empresa."""

    @pytest.fixture
    def empresa_loja_local_produto(self):
        empresa = Empresa.objects.create(
            nome_fantasia='Empresa Teste',
            razao_social='Empresa Teste Ltda',
            cnpj='98765432000100',
        )
        loja = Loja.objects.create(empresa=empresa, nome='Loja 1')
        categoria = CategoriaProduto.objects.create(nome='Cat')
        produto = Produto.objects.create(
            categoria=categoria,
            codigo_interno='TST001',
            descricao='Produto teste',
            classe_risco='OUTRA',
            ncm='36041000',
            unidade_comercial='UN',
            origem='0',
        )
        ProdutoParametrosEmpresa.objects.create(
            empresa=empresa,
            produto=produto,
            preco_venda=Decimal('10.00'),
            cfop_venda_dentro_uf='5102',
            csosn_cst='102',
            aliquota_icms=Decimal('18.00'),
        )
        local = LocalEstoque.objects.create(loja=loja, nome='Depósito')
        return empresa, loja, local, produto

    def test_primeira_entrada_define_custo_medio(self, empresa_loja_local_produto):
        empresa, _loja, _local, produto = empresa_loja_local_produto
        atualizar_custo_medio(empresa, produto, Decimal('100'), Decimal('10.00'))
        ev = EstoqueValorado.objects.get(empresa=empresa, produto=produto)
        assert ev.custo_medio == Decimal('10.0000')
        assert ev.quantidade_total == Decimal('100.000')

    def test_segunda_entrada_calcula_media_ponderada(self, empresa_loja_local_produto):
        empresa, _loja, local, produto = empresa_loja_local_produto
        atualizar_custo_medio(empresa, produto, Decimal('100'), Decimal('10.00'))
        EstoqueAtual.objects.create(
            produto=produto,
            local_estoque=local,
            quantidade=Decimal('100.000'),
        )
        atualizar_custo_medio(empresa, produto, Decimal('100'), Decimal('20.00'))
        ev = EstoqueValorado.objects.get(empresa=empresa, produto=produto)
        assert ev.custo_medio == Decimal('15.0000')
        assert ev.quantidade_total == Decimal('200.000')

    def test_entrada_sem_custo_ignorada(self, empresa_loja_local_produto):
        empresa, _loja, _local, produto = empresa_loja_local_produto
        atualizar_custo_medio(empresa, produto, Decimal('100'), None)
        assert not EstoqueValorado.objects.filter(empresa=empresa, produto=produto).exists()

    def test_saida_atualiza_quantidade_total(self, empresa_loja_local_produto):
        empresa, _loja, local, produto = empresa_loja_local_produto
        atualizar_custo_medio(empresa, produto, Decimal('100'), Decimal('10.00'))
        EstoqueAtual.objects.create(
            produto=produto,
            local_estoque=local,
            quantidade=Decimal('90.000'),
        )
        atualizar_quantidade_total(empresa, produto)
        ev = EstoqueValorado.objects.get(empresa=empresa, produto=produto)
        assert ev.quantidade_total == Decimal('90.000')

    def test_realizar_entrada_com_custo_cria_estoque_valorado(
        self, empresa_loja_local_produto
    ):
        empresa, _loja, local, produto = empresa_loja_local_produto
        realizar_movimento_estoque(
            produto=produto,
            tipo_movimento='ENTRADA',
            quantidade=Decimal('50.000'),
            local_destino=local,
            custo_unitario=Decimal('8.0000'),
        )
        ev = EstoqueValorado.objects.get(empresa=empresa, produto=produto)
        assert ev.custo_medio == Decimal('8.0000')
        assert ev.quantidade_total == Decimal('50.000')


def _parametros_padrao(empresa, produto):
    return ProdutoParametrosEmpresa.objects.create(
        empresa=empresa,
        produto=produto,
        preco_venda=Decimal('10.00'),
        cfop_venda_dentro_uf='5102',
        csosn_cst='102',
        aliquota_icms=Decimal('18.00'),
    )


@pytest.mark.django_db
class TestTransferenciaInterempresa:
    """Transferência entre CNPJs distintos (saída + entrada)."""

    @pytest.fixture
    def duas_empresas_produto(self):
        emp_a = Empresa.objects.create(
            nome_fantasia='Empresa A',
            razao_social='Empresa A LTDA',
            cnpj='11111111000191',
        )
        emp_b = Empresa.objects.create(
            nome_fantasia='Empresa B',
            razao_social='Empresa B LTDA',
            cnpj='22222222000182',
        )
        loja_a = Loja.objects.create(empresa=emp_a, nome='Loja A')
        loja_b = Loja.objects.create(empresa=emp_b, nome='Loja B')
        local_a = LocalEstoque.objects.create(loja=loja_a, nome='Dep A')
        local_a2 = LocalEstoque.objects.create(loja=loja_a, nome='Dep A2')
        local_b = LocalEstoque.objects.create(loja=loja_b, nome='Dep B')
        cat = CategoriaProduto.objects.create(nome='Cat IE')
        produto = Produto.objects.create(
            categoria=cat,
            codigo_interno='IE001',
            descricao='Prod IE',
            classe_risco='OUTRA',
            ncm='36041000',
            unidade_comercial='UN',
            origem='0',
        )
        params_a = _parametros_padrao(emp_a, produto)
        params_b = _parametros_padrao(emp_b, produto)
        return {
            'emp_a': emp_a,
            'emp_b': emp_b,
            'local_a': local_a,
            'local_a2': local_a2,
            'local_b': local_b,
            'produto': produto,
            'params_b': params_b,
            'params_a': params_a,
        }

    def test_transferencia_entre_empresas_distintas(self, duas_empresas_produto):
        c = duas_empresas_produto
        realizar_movimento_estoque(
            produto=c['produto'],
            tipo_movimento='ENTRADA',
            quantidade=Decimal('100.000'),
            local_destino=c['local_a'],
            custo_unitario=Decimal('10.0000'),
        )

        transferencia = executar_transferencia_interempresa(
            produto=c['produto'],
            local_origem=c['local_a'],
            local_destino=c['local_b'],
            quantidade=Decimal('30'),
            custo_unitario=Decimal('10.0000'),
        )

        assert transferencia.status == 'CONCLUIDA'
        assert TransferenciaInterempresa.objects.filter(pk=transferencia.pk).exists()
        assert transferencia.movimento_saida.tipo_movimento == 'SAIDA'
        assert transferencia.movimento_entrada.tipo_movimento == 'ENTRADA'

        estoque_a = EstoqueAtual.objects.get(
            produto=c['produto'], local_estoque=c['local_a']
        )
        assert estoque_a.quantidade == Decimal('70.000')

        estoque_b = EstoqueAtual.objects.get(
            produto=c['produto'], local_estoque=c['local_b']
        )
        assert estoque_b.quantidade == Decimal('30.000')

    def test_transferencia_mesma_empresa_lanca_erro(self, duas_empresas_produto):
        c = duas_empresas_produto
        with pytest.raises(ValidationError):
            executar_transferencia_interempresa(
                produto=c['produto'],
                local_origem=c['local_a'],
                local_destino=c['local_a2'],
                quantidade=Decimal('10'),
                custo_unitario=Decimal('6.0000'),
            )

    def test_transferencia_produto_inativo_na_empresa_destino(
        self, duas_empresas_produto
    ):
        c = duas_empresas_produto
        c['params_b'].ativo_nessa_empresa = False
        c['params_b'].save()
        realizar_movimento_estoque(
            produto=c['produto'],
            tipo_movimento='ENTRADA',
            quantidade=Decimal('100.000'),
            local_destino=c['local_a'],
            custo_unitario=Decimal('10.0000'),
        )
        with pytest.raises(ValidationError):
            executar_transferencia_interempresa(
                produto=c['produto'],
                local_origem=c['local_a'],
                local_destino=c['local_b'],
                quantidade=Decimal('10'),
                custo_unitario=Decimal('10.0000'),
            )

    def test_transferencia_nao_usa_tipo_transferencia_entre_cnpjs(
        self, duas_empresas_produto
    ):
        c = duas_empresas_produto
        realizar_movimento_estoque(
            produto=c['produto'],
            tipo_movimento='ENTRADA',
            quantidade=Decimal('50.000'),
            local_destino=c['local_a'],
            custo_unitario=Decimal('10.0000'),
        )
        realizar_movimento_estoque(
            produto=c['produto'],
            tipo_movimento='ENTRADA',
            quantidade=Decimal('1.000'),
            local_destino=c['local_b'],
            custo_unitario=Decimal('10.0000'),
        )
        with pytest.raises(ValueError, match='interempresa'):
            realizar_movimento_estoque(
                produto=c['produto'],
                tipo_movimento='TRANSFERENCIA',
                quantidade=Decimal('1.000'),
                local_origem=c['local_a'],
                local_destino=c['local_b'],
            )

