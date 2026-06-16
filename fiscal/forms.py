"""
Forms do módulo fiscal.
"""
from django import forms
from django.forms import formset_factory, BaseFormSet
from django.core.exceptions import ValidationError
from decimal import Decimal
from datetime import date

from .models import (
    NotaFiscalEntrada,
    ItemNotaFiscalEntrada,
    ConfiguracaoFiscalLoja,
    NotaFiscalConsumidor,
    NotaFiscalServico,
)
from pessoas.models import Fornecedor
from core.models import Loja
from produtos.models import Produto


class NotaFiscalEntradaForm(forms.ModelForm):
    """Formulário para digitação manual de Nota Fiscal de Entrada."""

    class Meta:
        model = NotaFiscalEntrada
        fields = [
            'loja', 'fornecedor', 'numero', 'serie', 'chave_acesso',
            'valor_total', 'data_emissao', 'data_entrada'
        ]
        widgets = {
            'loja': forms.Select(attrs={'class': 'form-control', 'required': True}),
            'fornecedor': forms.Select(attrs={'class': 'form-control', 'required': True}),
            'numero': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': 1,
                'required': True,
                'placeholder': 'Ex: 12345',
            }),
            'serie': forms.TextInput(attrs={
                'class': 'form-control',
                'maxlength': 3,
                'required': True,
                'placeholder': 'Ex: 001',
            }),
            'chave_acesso': forms.TextInput(attrs={
                'class': 'form-control',
                'maxlength': 44,
                'required': True,
                'placeholder': '44 dígitos da chave de acesso',
            }),
            'valor_total': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0.01',
                'required': True,
            }),
            'data_emissao': forms.DateInput(attrs={
                'type': 'date',
                'class': 'form-control',
                'required': True,
            }),
            'data_entrada': forms.DateInput(attrs={
                'type': 'date',
                'class': 'form-control',
                'required': True,
            }),
        }

    def __init__(self, *args, **kwargs):
        empresa = kwargs.pop('empresa', None)
        super().__init__(*args, **kwargs)
        if empresa:
            self.fields['loja'].queryset = Loja.objects.filter(empresa=empresa, is_active=True)
            self.fields['fornecedor'].queryset = Fornecedor.objects.filter(empresa=empresa, is_active=True)
        else:
            self.fields['loja'].queryset = Loja.objects.none()
            self.fields['fornecedor'].queryset = Fornecedor.objects.none()

        if not self.instance.pk:
            self.fields['data_entrada'].initial = date.today()
            self.fields['data_emissao'].initial = date.today()

    def clean_chave_acesso(self):
        chave = self.cleaned_data.get('chave_acesso', '').strip()
        if chave and len(chave) != 44:
            raise ValidationError('A chave de acesso deve ter exatamente 44 dígitos.')
        if chave and not chave.isdigit():
            raise ValidationError('A chave de acesso deve conter apenas números.')
        return chave

    def clean_valor_total(self):
        valor = self.cleaned_data.get('valor_total')
        if valor is not None and valor <= 0:
            raise ValidationError('O valor total deve ser maior que zero.')
        return valor

    def clean_data_entrada(self):
        data_emissao = self.cleaned_data.get('data_emissao')
        data_entrada = self.cleaned_data.get('data_entrada')
        if data_emissao and data_entrada and data_entrada < data_emissao:
            raise ValidationError('A data de entrada não pode ser anterior à data de emissão.')
        return data_entrada


class ItemNotaFiscalEntradaForm(forms.Form):
    """
    Formulário para item de NF-e na digitação manual.
    Campos: produto, quantidade, preco_unitario, local_estoque (opcional).
    Formulários vazios são ignorados (formset permite linhas em branco).
    """
    produto = forms.ModelChoiceField(
        queryset=Produto.objects.none(),
        required=False,
        label='Produto',
        widget=forms.Select(attrs={'class': 'form-control form-control-sm'})
    )
    quantidade = forms.DecimalField(
        min_value=Decimal('0.001'),
        max_digits=10,
        decimal_places=3,
        required=False,
        label='Quantidade',
        widget=forms.NumberInput(attrs={
            'class': 'form-control form-control-sm',
            'step': '0.001',
            'placeholder': 'Ex: 10',
        })
    )
    preco_unitario = forms.DecimalField(
        min_value=Decimal('0.0001'),
        max_digits=12,
        decimal_places=4,
        required=False,
        label='Preço Unit.',
        widget=forms.NumberInput(attrs={
            'class': 'form-control form-control-sm',
            'step': '0.0001',
            'placeholder': 'Ex: 1,50',
        })
    )
    local_estoque = forms.ModelChoiceField(
        queryset=None,
        required=False,
        label='Local Estoque',
        widget=forms.Select(attrs={'class': 'form-control form-control-sm'}),
        empty_label='(Padrão)'
    )

    def clean(self):
        data = super().clean()
        produto = data.get('produto')
        quantidade = data.get('quantidade')
        preco = data.get('preco_unitario')
        if produto or quantidade is not None or preco is not None:
            if not produto:
                raise ValidationError('Produto é obrigatório quando há quantidade ou preço.')
            if quantidade is None or quantidade <= 0:
                raise ValidationError('Quantidade inválida.')
            if preco is None or preco <= 0:
                raise ValidationError('Preço unitário inválido.')
        return data

    def __init__(self, *args, loja=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['produto'].queryset = Produto.objects.filter(is_active=True).order_by('descricao')
        if loja:
            from estoque.models import LocalEstoque
            self.fields['local_estoque'].queryset = LocalEstoque.objects.filter(
                loja=loja, is_active=True
            ).order_by('nome')
        else:
            from estoque.models import LocalEstoque
            self.fields['local_estoque'].queryset = LocalEstoque.objects.none()


class BaseItemNotaFiscalEntradaFormSet(BaseFormSet):
    """Formset que passa loja para cada form e valida totais."""

    def __init__(self, *args, loja=None, **kwargs):
        self.loja = loja
        super().__init__(*args, **kwargs)

    def _construct_form(self, i, **kwargs):
        kwargs['loja'] = self.loja
        return super()._construct_form(i, **kwargs)

    def clean(self):
        from .services_entrada import validar_totais, TOLERANCIA_MANUAL

        itens_com_dados = [f for f in self.forms if f.cleaned_data and f.cleaned_data.get('produto')]
        if not itens_com_dados:
            return

        itens_valores = [
            cd['quantidade'] * cd['preco_unitario']
            for cd in (f.cleaned_data for f in itens_com_dados)
            if cd.get('produto')
        ]
        if not itens_valores:
            return

        valor_total_str = self.data.get('valor_total', '')
        if not valor_total_str:
            return
        try:
            nota_valor_total = Decimal(str(valor_total_str).replace(',', '.'))
        except (ValueError, TypeError):
            return

        validar_totais(nota_valor_total, itens_valores, tolerancia=TOLERANCIA_MANUAL)


ItemNotaFiscalEntradaFormSet = formset_factory(
    ItemNotaFiscalEntradaForm,
    formset=BaseItemNotaFiscalEntradaFormSet,
    extra=3,
    min_num=0,
    validate_min=True,
    max_num=50,
    validate_max=True,
)


class ConfiguracaoFiscalLojaForm(forms.ModelForm):
    """
    Formulario de cadastro / edicao da configuracao fiscal de loja.
    """

    REGIME_CHOICES = [
        ("", "Selecione o regime..."),
        ("SIMPLES_NACIONAL", "Simples Nacional"),
        ("LUCRO_PRESUMIDO", "Lucro Presumido"),
        ("LUCRO_REAL", "Lucro Real"),
    ]

    regime_tributario = forms.ChoiceField(
        label="Regime Tributario",
        choices=REGIME_CHOICES,
        widget=forms.Select(attrs={"class": "form-control"}),
    )

    class Meta:
        model = ConfiguracaoFiscalLoja
        fields = [
            "loja",
            "cnpj",
            "inscricao_estadual",
            "regime_tributario",
            "certificado_arquivo",
            "senha_certificado",
            "ambiente",
            "serie_nfe",
            "serie_nfce",
            "proximo_numero_nfe",
            "proximo_numero_nfce",
            "inscricao_municipal",
            "codigo_cnae",
            "serie_rps",
            "proximo_numero_rps",
            "csc_id",
            "csc_token",
            "usar_reforma_2026",
            "aliquota_ibs_padrao_2026",
            "aliquota_cbs_padrao_2026",
        ]
        widgets = {
            "loja": forms.Select(attrs={"class": "form-control"}),
            "cnpj": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "00.000.000/0000-00",
                "maxlength": 18,
            }),
            "inscricao_estadual": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Inscricao Estadual",
            }),
            "certificado_arquivo": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "/caminho/no/servidor/certificado.pfx",
            }),
            "senha_certificado": forms.PasswordInput(
                render_value=False,
                attrs={"class": "form-control", "placeholder": "Senha do certificado A1"},
            ),
            "ambiente": forms.Select(attrs={"class": "form-control"}),
            "serie_nfe": forms.TextInput(attrs={"class": "form-control", "maxlength": 3, "placeholder": "001"}),
            "serie_nfce": forms.TextInput(attrs={"class": "form-control", "maxlength": 3, "placeholder": "001"}),
            "proximo_numero_nfe": forms.NumberInput(attrs={"class": "form-control", "min": 1}),
            "proximo_numero_nfce": forms.NumberInput(attrs={"class": "form-control", "min": 1}),
            "inscricao_municipal": forms.TextInput(attrs={"class": "form-control"}),
            "codigo_cnae": forms.TextInput(attrs={"class": "form-control", "maxlength": 7}),
            "serie_rps": forms.TextInput(attrs={"class": "form-control", "maxlength": 5}),
            "proximo_numero_rps": forms.NumberInput(attrs={"class": "form-control", "min": 1}),
            "csc_id": forms.TextInput(attrs={"class": "form-control", "maxlength": 6}),
            "csc_token": forms.TextInput(attrs={"class": "form-control", "maxlength": 36}),
            "usar_reforma_2026": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "aliquota_ibs_padrao_2026": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "aliquota_cbs_padrao_2026": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
        }

    def __init__(self, *args, **kwargs):
        empresa = kwargs.pop("empresa", None)
        super().__init__(*args, **kwargs)
        loja_base = Loja.objects.filter(is_active=True)
        if empresa:
            loja_base = loja_base.filter(empresa=empresa)
        if self.instance and self.instance.pk:
            self.fields["loja"].queryset = loja_base
        else:
            lojas_com_config = ConfiguracaoFiscalLoja.objects.values_list("loja_id", flat=True)
            self.fields["loja"].queryset = (
                loja_base.exclude(id__in=lojas_com_config).order_by("empresa__nome_fantasia", "nome")
            )
        self.fields["loja"].empty_label = "Selecione a loja..."

    def save(self, commit=True):
        # Em edicao, senha vazia nao deve sobrescrever o valor existente.
        instance = super().save(commit=False)
        if instance.pk and "senha_certificado" in self.cleaned_data and not self.cleaned_data.get("senha_certificado"):
            original_obj = ConfiguracaoFiscalLoja.objects.filter(pk=instance.pk).first()
            original = original_obj.senha_certificado if original_obj else None
            instance.senha_certificado = original
        if commit:
            instance.save()
        return instance


class ConfiguracaoFiscalLojaAdminForm(ConfiguracaoFiscalLojaForm):
    """Admin: todos os campos do model (incl. BaseModel) e mesma proteção de senha."""

    class Meta(ConfiguracaoFiscalLojaForm.Meta):
        fields = "__all__"


class NotaFiscalConsumidorForm(forms.ModelForm):
    """Formulário de NFC-e."""

    class Meta:
        model = NotaFiscalConsumidor
        fields = [
            'loja', 'modalidade', 'ambiente',
            'cpf_consumidor', 'nome_consumidor',
            'forma_pagamento', 'valor_pago', 'valor_troco', 'valor_desconto',
        ]
        widgets = {
            'loja': forms.Select(attrs={'class': 'form-control'}),
            'modalidade': forms.Select(attrs={'class': 'form-control'}),
            'ambiente': forms.Select(attrs={'class': 'form-control'}),
            'cpf_consumidor': forms.TextInput(attrs={'class': 'form-control'}),
            'nome_consumidor': forms.TextInput(attrs={'class': 'form-control'}),
            'forma_pagamento': forms.TextInput(attrs={'class': 'form-control'}),
            'valor_pago': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'valor_troco': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'valor_desconto': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
        }

    def __init__(self, *args, **kwargs):
        empresa = kwargs.pop('empresa', None)
        super().__init__(*args, **kwargs)
        qs = Loja.objects.filter(is_active=True)
        if empresa:
            qs = qs.filter(empresa=empresa)
        self.fields['loja'].queryset = qs


class NotaFiscalServicoForm(forms.ModelForm):
    """Formulário de NFS-e."""

    class Meta:
        model = NotaFiscalServico
        fields = [
            'loja', 'nome_tomador', 'cpf_cnpj_tomador', 'email_tomador',
            'municipio_tomador', 'codigo_servico', 'discriminacao',
            'municipio_prestacao', 'valor_servico', 'valor_deducoes',
            'aliquota_iss', 'iss_retido',
        ]
        widgets = {
            'loja': forms.Select(attrs={'class': 'form-control'}),
            'nome_tomador': forms.TextInput(attrs={'class': 'form-control'}),
            'cpf_cnpj_tomador': forms.TextInput(attrs={'class': 'form-control'}),
            'email_tomador': forms.EmailInput(attrs={'class': 'form-control'}),
            'municipio_tomador': forms.TextInput(attrs={'class': 'form-control', 'maxlength': 7}),
            'codigo_servico': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '01.01'}),
            'discriminacao': forms.Textarea(attrs={'class': 'form-control', 'rows': 4}),
            'municipio_prestacao': forms.TextInput(attrs={'class': 'form-control', 'maxlength': 7}),
            'valor_servico': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'valor_deducoes': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'aliquota_iss': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.0001'}),
            'iss_retido': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, **kwargs):
        empresa = kwargs.pop('empresa', None)
        super().__init__(*args, **kwargs)
        qs = Loja.objects.filter(is_active=True)
        if empresa:
            qs = qs.filter(empresa=empresa)
        self.fields['loja'].queryset = qs
