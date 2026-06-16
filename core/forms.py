"""
Formularios do app core.
"""
from django import forms

from .models import Empresa, Loja

_FC = "form-control"

UF_CHOICES = [
    ("", "UF"),
    ("AC", "AC"), ("AL", "AL"), ("AP", "AP"), ("AM", "AM"),
    ("BA", "BA"), ("CE", "CE"), ("DF", "DF"), ("ES", "ES"),
    ("GO", "GO"), ("MA", "MA"), ("MT", "MT"), ("MS", "MS"),
    ("MG", "MG"), ("PA", "PA"), ("PB", "PB"), ("PR", "PR"),
    ("PE", "PE"), ("PI", "PI"), ("RJ", "RJ"), ("RN", "RN"),
    ("RS", "RS"), ("RO", "RO"), ("RR", "RR"), ("SC", "SC"),
    ("SP", "SP"), ("SE", "SE"), ("TO", "TO"),
]


class EmpresaForm(forms.ModelForm):
    """Formulario de cadastro / edicao de Empresa."""

    class Meta:
        model = Empresa
        fields = [
            "nome_fantasia", "razao_social", "cnpj", "inscricao_estadual",
            "telefone", "email",
            "logradouro", "numero", "complemento", "bairro",
            "cidade", "uf", "cep",
            "is_active",
        ]
        widgets = {
            "nome_fantasia": forms.TextInput(attrs={
                "class": _FC, "placeholder": "Ex: Guardião Comércio",
            }),
            "razao_social": forms.TextInput(attrs={
                "class": _FC, "placeholder": "Razao Social completa",
            }),
            "cnpj": forms.TextInput(attrs={
                "class": _FC, "placeholder": "00.000.000/0000-00", "maxlength": 18,
            }),
            "inscricao_estadual": forms.TextInput(attrs={
                "class": _FC, "placeholder": "IE (opcional)",
            }),
            "telefone": forms.TextInput(attrs={
                "class": _FC, "placeholder": "(00) 00000-0000",
            }),
            "email": forms.EmailInput(attrs={
                "class": _FC, "placeholder": "contato@empresa.com.br",
            }),
            "logradouro": forms.TextInput(attrs={"class": _FC}),
            "numero": forms.TextInput(attrs={"class": _FC, "placeholder": "S/N"}),
            "complemento": forms.TextInput(attrs={"class": _FC}),
            "bairro": forms.TextInput(attrs={"class": _FC}),
            "cidade": forms.TextInput(attrs={"class": _FC}),
            "uf": forms.Select(attrs={"class": _FC}, choices=UF_CHOICES),
            "cep": forms.TextInput(attrs={"class": _FC, "placeholder": "00000-000", "maxlength": 9}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }
        labels = {
            "is_active": "Empresa ativa",
        }


class LojaForm(forms.ModelForm):
    """Formulario de cadastro / edicao de Loja."""

    class Meta:
        model = Loja
        fields = [
            "empresa", "nome", "cnpj", "inscricao_estadual",
            "telefone", "email",
            "logradouro", "numero", "complemento", "bairro",
            "cidade", "uf", "cep",
            "is_active",
        ]
        widgets = {
            "empresa": forms.Select(attrs={"class": _FC}),
            "nome": forms.TextInput(attrs={
                "class": _FC, "placeholder": "Ex: Loja Centro",
            }),
            "cnpj": forms.TextInput(attrs={
                "class": _FC, "placeholder": "00.000.000/0000-00", "maxlength": 18,
            }),
            "inscricao_estadual": forms.TextInput(attrs={
                "class": _FC, "placeholder": "IE (opcional)",
            }),
            "telefone": forms.TextInput(attrs={
                "class": _FC, "placeholder": "(00) 00000-0000",
            }),
            "email": forms.EmailInput(attrs={
                "class": _FC, "placeholder": "loja@empresa.com.br",
            }),
            "logradouro": forms.TextInput(attrs={"class": _FC}),
            "numero": forms.TextInput(attrs={"class": _FC, "placeholder": "S/N"}),
            "complemento": forms.TextInput(attrs={"class": _FC}),
            "bairro": forms.TextInput(attrs={"class": _FC}),
            "cidade": forms.TextInput(attrs={"class": _FC}),
            "uf": forms.Select(attrs={"class": _FC}, choices=UF_CHOICES),
            "cep": forms.TextInput(attrs={"class": _FC, "placeholder": "00000-000", "maxlength": 9}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }
        labels = {
            "is_active": "Loja ativa",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["empresa"].queryset = Empresa.objects.filter(is_active=True).order_by("nome_fantasia")
        self.fields["empresa"].empty_label = "Selecione a empresa..."
