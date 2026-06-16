# Manual de Cadastro - Empresa, Loja e Produtos

Este guia foi feito para usuarios administrativos do Guardiao que precisam iniciar o sistema em producao.

## 1) Acesso necessario

- Entre com um usuario com perfil **Administrador** (ou superusuario).
- No menu lateral, voce deve visualizar:
  - `Administração > Empresas`
  - `Administração > Lojas`
  - `Administração > Config. Fiscal`
  - `Cadastros > Produtos`

## 2) Cadastro da Empresa

1. Acesse `Administração > Empresas`.
2. Clique em **Nova Empresa**.
3. Preencha os campos principais:
   - Nome Fantasia
   - Razao Social
   - CNPJ
4. Preencha contato e endereco.
5. Marque **Empresa ativa**.
6. Clique em **Criar**.

## 3) Cadastro da Loja

1. Acesse `Administração > Lojas`.
2. Clique em **Nova Loja**.
3. Selecione a **Empresa** cadastrada.
4. Preencha:
   - Nome da loja
   - CNPJ (da filial, quando houver)
   - Contato e endereco
5. Marque **Loja ativa**.
6. Clique em **Criar**.

## 4) Configuracao Fiscal da Loja

1. Acesse `Administração > Config. Fiscal`.
2. Clique em **Nova Configuração**.
3. Selecione a loja que vai emitir nota.
4. Preencha:
   - CNPJ e Inscricao Estadual
   - Regime tributario
   - Ambiente (`HOMOLOGACAO` para testes iniciais)
   - Serie e proximo numero da NF-e/NFC-e
5. Se ja tiver certificado, informe caminho do `.pfx` e senha.
6. Salve em **Criar**.

Boas praticas:
- Comece em **Homologacao**.
- So altere para **Producao** quando a validacao fiscal estiver concluida.

## 5) Cadastro de Produtos

1. Acesse `Cadastros > Produtos`.
2. Clique em **Novo Produto**.
3. Preencha os campos obrigatorios do cadastro.
4. Defina preco de venda e status ativo.
5. Salve.

Se usar codigos alternativos:
1. Abra a lista de produtos.
2. No produto desejado, clique em **Códigos**.
3. Cadastre os codigos de barras alternativos e multiplicadores.

## 6) Ordem recomendada para iniciar operacao

1. Empresa
2. Loja
3. Configuracao Fiscal da Loja
4. Produtos
5. Clientes/Fornecedores (se necessario)
6. Testes de operacao no PDV

## 7) Erros comuns e como resolver

- **Nao aparece menu Administracao**
  - Verifique se o usuario pertence ao grupo ADMINISTRADOR ou e superusuario.

- **Loja nao aparece em Config. Fiscal**
  - A loja pode estar inativa, ou ja possuir configuracao fiscal cadastrada.

- **Campos fiscais invalidos**
  - Revise CNPJ, inscricao estadual e regime tributario antes de salvar.

## 8) Central de Guias no sistema

O sistema possui uma area para consulta de guias:

- Menu: `Sistema > Guias de Utilização`
- Qualquer usuario logado pode consultar os guias publicados.
- A publicacao e manutencao dos guias e feita no Admin Django, no cadastro **Guias de Uso**.
