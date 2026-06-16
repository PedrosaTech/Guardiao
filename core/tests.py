"""
Testes do app core.
"""
import pytest
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.contrib.sessions.middleware import SessionMiddleware
from django.core.exceptions import PermissionDenied
from django.test import Client
from django.urls import reverse

from .models import Empresa, Loja, UsuarioEmpresa
from .tenant import SESSION_KEY, get_empresa_ativa, set_empresa_ativa

User = get_user_model()


def _add_session(request):
    middleware = SessionMiddleware(lambda req: None)
    middleware.process_request(request)
    request.session.save()


@pytest.mark.django_db
class TestTenantSession:
    """Contexto de empresa na sessão (Fase 1 multitenancy)."""

    @pytest.fixture
    def empresa(self):
        return Empresa.objects.create(
            nome_fantasia='Empresa A',
            razao_social='Empresa A LTDA',
            cnpj='11111111000191',
        )

    @pytest.fixture
    def user(self):
        return User.objects.create_user('tenant_user', password='pass12345')

    def test_get_empresa_ativa_sem_sessao_lanca(self, rf, user):
        request = rf.get('/')
        request.user = user
        _add_session(request)
        with pytest.raises(PermissionDenied):
            get_empresa_ativa(request)

    def test_get_empresa_ativa_empresa_nao_permitida(self, rf, user, empresa):
        request = rf.get('/')
        request.user = user
        _add_session(request)
        UsuarioEmpresa.objects.create(user=user, empresa=empresa, perfil='OPERADOR')
        request.session[SESSION_KEY] = 99999
        with pytest.raises(PermissionDenied):
            get_empresa_ativa(request)

    def test_set_empresa_ativa_grava_sessao(self, rf, user, empresa):
        request = rf.get('/')
        request.user = user
        _add_session(request)
        UsuarioEmpresa.objects.create(user=user, empresa=empresa, perfil='OPERADOR')
        set_empresa_ativa(request, empresa.id)
        assert request.session[SESSION_KEY] == empresa.id

    def test_set_empresa_ativa_sem_vinculo_lanca(self, rf, user, empresa):
        request = rf.get('/')
        request.user = user
        _add_session(request)
        with pytest.raises(PermissionDenied):
            set_empresa_ativa(request, empresa.id)

    def test_middleware_carrega_empresa_padrao(self, client, user, empresa):
        UsuarioEmpresa.objects.create(
            user=user,
            empresa=empresa,
            perfil='OPERADOR',
            empresa_padrao=True,
        )
        client.force_login(user)
        client.get('/')
        assert client.session.get(SESSION_KEY) == empresa.id


@pytest.mark.django_db
class TestEmpresa:
    """Testes para o modelo Empresa."""
    
    def test_criar_empresa(self):
        """Testa criação de empresa."""
        empresa = Empresa.objects.create(
            nome_fantasia='Guardião',
            razao_social='Guardião Ltda',
            cnpj='12345678000190',
        )
        assert empresa.id is not None
        assert empresa.nome_fantasia == 'Guardião'
        assert empresa.is_active is True
    
    def test_criar_loja(self):
        """Testa criação de loja."""
        empresa = Empresa.objects.create(
            nome_fantasia='Guardião',
            razao_social='Guardião Ltda',
            cnpj='12345678000190',
        )
        loja = Loja.objects.create(
            empresa=empresa,
            nome='Loja Centro',
            cnpj='12345678000190',
        )
        assert loja.id is not None
        assert loja.empresa == empresa
        assert loja.nome == 'Loja Centro'
        assert loja.is_active is True


@pytest.mark.django_db
class TestIdorEmpresaAtiva:
    """Vazamento de dados entre empresas (Fase 4)."""

    def test_usuario_nao_acessa_pedido_de_outra_empresa(self, client):
        from pessoas.models import Cliente
        from vendas.models import CondicaoPagamento, PedidoVenda

        User = get_user_model()
        user = User.objects.create_user('idor_user', password='secret123')
        emp_a = Empresa.objects.create(
            nome_fantasia='Empresa A',
            razao_social='A LTDA',
            cnpj='11111111000191',
        )
        emp_b = Empresa.objects.create(
            nome_fantasia='Empresa B',
            razao_social='B LTDA',
            cnpj='22222222000192',
        )
        UsuarioEmpresa.objects.create(user=user, empresa=emp_a, perfil='OPERADOR', empresa_padrao=True)
        loja_b = Loja.objects.create(empresa=emp_b, nome='Loja B', cnpj='22222222000192')
        cliente_b = Cliente.objects.create(
            empresa=emp_b,
            tipo_pessoa='PF',
            nome_razao_social='Cliente B',
            cpf_cnpj='12345678901',
        )
        cond_b = CondicaoPagamento.objects.create(
            empresa=emp_b,
            nome='À vista',
            numero_parcelas=1,
            dias_entre_parcelas=0,
        )
        pedido_b = PedidoVenda.objects.create(
            loja=loja_b,
            cliente=cliente_b,
            tipo_venda='BALCAO',
            vendedor=user,
            condicao_pagamento=cond_b,
            valor_total=Decimal('1.00'),
        )

        client.force_login(user)
        session = client.session
        session[SESSION_KEY] = emp_a.id
        session.save()

        url = reverse('vendas:detalhes_pedido', kwargs={'pedido_id': pedido_b.id})
        response = client.get(url)
        assert response.status_code == 404

    def test_lista_criar_pedido_so_lojas_da_empresa_ativa(self, client):
        User = get_user_model()
        user = User.objects.create_user('idor_user2', password='secret123')
        emp_a = Empresa.objects.create(
            nome_fantasia='Empresa A2',
            razao_social='A2 LTDA',
            cnpj='33333333000193',
        )
        emp_b = Empresa.objects.create(
            nome_fantasia='Empresa B2',
            razao_social='B2 LTDA',
            cnpj='44444444000194',
        )
        UsuarioEmpresa.objects.create(user=user, empresa=emp_a, perfil='OPERADOR', empresa_padrao=True)
        UsuarioEmpresa.objects.create(user=user, empresa=emp_b, perfil='OPERADOR')
        Loja.objects.create(empresa=emp_a, nome='Loja A2', cnpj='33333333000193')
        Loja.objects.create(empresa=emp_b, nome='Loja B2', cnpj='44444444000194')

        client.force_login(user)
        session = client.session
        session[SESSION_KEY] = emp_a.id
        session.save()

        response = client.get(reverse('vendas:criar_pedido'))
        assert response.status_code == 200
        lojas_ctx = response.context['lojas']
        assert all(l.empresa_id == emp_a.id for l in lojas_ctx)

