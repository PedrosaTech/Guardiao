# 📋 Campos Fiscais dos Produtos - Guardião

## ✅ Campos Implementados

### Campos Já Existentes (Mantidos)

1. **NCM** - Nomenclatura Comum do Mercosul
   - Tipo: `CharField(max_length=10)`
   - Exemplo: `3604.10.00`
   - ✅ Já existia

2. **CEST** - Código Especificador da Substituição Tributária
   - Tipo: `CharField(max_length=10, blank=True, null=True)`
   - Exemplo: `09.001.00`
   - ✅ Já existia

3. **CFOP Venda Dentro UF** - Código Fiscal de Operações e Prestações
   - Tipo: `CharField(max_length=4)`
   - Exemplo: `5.102`
   - ✅ Já existia como `cfop_venda_dentro_uf`

4. **CFOP Venda Fora UF**
   - Tipo: `CharField(max_length=4, blank=True, null=True)`
   - Exemplo: `6.102`
   - ✅ Já existia como `cfop_venda_fora_uf`

5. **CSOSN/CST ICMS** - Código de Situação da Operação no Simples Nacional / Código de Situação Tributária
   - Tipo: `CharField(max_length=3)`
   - Exemplo: `102` (Simples) ou `00` (Regime Normal)
   - ✅ Já existia como `csosn_cst`

6. **Alíquota ICMS**
   - Tipo: `DecimalField(max_digits=5, decimal_places=2)`
   - Padrão: `18.00%` (BA)
   - ✅ Já existia como `aliquota_icms` (padrão atualizado para 18%)

### Novos Campos Adicionados

#### 1. ICMS-ST (Substituição Tributária)

- **`icms_st_cst`** - CST/CSOSN ICMS-ST
  - Tipo: `CharField(max_length=3, blank=True, null=True)`
  - Exemplo: `10` (CST) ou `201` (CSOSN)
  - Uso: Somente se o estado de destino exigir

- **`aliquota_icms_st`** - Alíquota ICMS-ST (%)
  - Tipo: `DecimalField(max_digits=5, decimal_places=2, default=0.00)`
  - Padrão: `0.00%`
  - Uso: Alíquota de ICMS-ST se aplicável

#### 2. PIS (Programa de Integração Social)

- **`pis_cst`** - CST PIS
  - Tipo: `CharField(max_length=2, default='01')`
  - Padrão: `01` (Operação Tributável com Alíquota Básica)
  - Exemplo: `01`

- **`aliquota_pis`** - Alíquota PIS (%)
  - Tipo: `DecimalField(max_digits=5, decimal_places=2, default=1.65)`
  - Padrão: `1.65%`
  - Exemplo: `1,65%`

#### 3. COFINS (Contribuição para o Financiamento da Seguridade Social)

- **`cofins_cst`** - CST COFINS
  - Tipo: `CharField(max_length=2, default='01')`
  - Padrão: `01` (Operação Tributável com Alíquota Básica)
  - Exemplo: `01`

- **`aliquota_cofins`** - Alíquota COFINS (%)
  - Tipo: `DecimalField(max_digits=5, decimal_places=2, default=7.60)`
  - Padrão: `7.60%`
  - Exemplo: `7,6%`

#### 4. IPI na Venda (Imposto sobre Produtos Industrializados)

- **`ipi_venda_cst`** - CST IPI Venda
  - Tipo: `CharField(max_length=2, default='52')`
  - Padrão: `52` (Saída Tributada com Alíquota Zero)
  - Exemplo: `52`

- **`aliquota_ipi_venda`** - Alíquota IPI Venda (%)
  - Tipo: `DecimalField(max_digits=5, decimal_places=2, default=0.00)`
  - Padrão: `0.00%`
  - Exemplo: `0%` (geralmente zero na venda)

#### 5. IPI na Compra

- **`ipi_compra_cst`** - CST IPI Compra
  - Tipo: `CharField(max_length=2, default='02')`
  - Padrão: `02` (Entrada Tributada)
  - Exemplo: `02`

- **`aliquota_ipi_compra`** - Alíquota IPI Compra (%)
  - Tipo: `DecimalField(max_digits=5, decimal_places=2, default=0.00, blank=True, null=True)`
  - Padrão: `0.00%`
  - Uso: Conforme NF do fornecedor

## 📊 Valores Padrão Configurados

| Campo | Valor Padrão | Descrição |
|-------|--------------|-----------|
| `ncm` | - | Obrigatório (ex: 3604.10.00) |
| `cest` | - | Opcional (ex: 09.001.00) |
| `cfop_venda_dentro_uf` | - | Obrigatório (ex: 5.102) |
| `cfop_venda_fora_uf` | - | Opcional (ex: 6.102) |
| `csosn_cst` | - | Obrigatório (ex: 102 ou 00) |
| `aliquota_icms` | 18.00% | Padrão BA |
| `icms_st_cst` | - | Opcional (ex: 10 ou 201) |
| `aliquota_icms_st` | 0.00% | Se aplicável |
| `pis_cst` | 01 | Operação Tributável |
| `aliquota_pis` | 1.65% | Padrão |
| `cofins_cst` | 01 | Operação Tributável |
| `aliquota_cofins` | 7.60% | Padrão |
| `ipi_venda_cst` | 52 | Alíquota Zero |
| `aliquota_ipi_venda` | 0.00% | Geralmente zero |
| `ipi_compra_cst` | 02 | Entrada Tributada |
| `aliquota_ipi_compra` | 0.00% | Conforme NF fornecedor |

## 🎨 Organização no Admin

Os campos foram organizados em fieldsets:

1. **Dados Fiscais - NCM, CEST e CFOP**
   - NCM, CEST, CFOPs, Unidade, Origem

2. **Dados Fiscais - ICMS**
   - CSOSN/CST ICMS, Alíquota ICMS, ICMS-ST

3. **Dados Fiscais - PIS e COFINS**
   - CST e Alíquotas de PIS e COFINS

4. **Dados Fiscais - IPI**
   - CST e Alíquotas de IPI (Venda e Compra)

## 📝 Migração

Uma migração foi criada automaticamente:

```
produtos/migrations/0003_produto_aliquota_cofins_produto_aliquota_icms_st_and_more.py
```

**Para aplicar a migração:**

```bash
python manage.py migrate produtos
```

## ✅ Status

- ✅ Todos os campos fiscais necessários implementados
- ✅ Valores padrão configurados conforme especificação
- ✅ Admin organizado em fieldsets lógicos
- ✅ Migração criada e pronta para aplicar
- ✅ Help texts adicionados para facilitar preenchimento

## 🔍 Validações Futuras (TODOs)

- [ ] Validar formato do NCM (8 dígitos)
- [ ] Validar formato do CEST (7 dígitos com pontos)
- [ ] Validar formato do CFOP (4 dígitos)
- [ ] Validar CSTs conforme tabelas oficiais
- [ ] Validar alíquotas dentro de faixas permitidas
- [ ] Criar choices para CSTs mais comuns

