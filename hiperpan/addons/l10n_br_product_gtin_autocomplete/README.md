# Brazilian Product GTIN Autocomplete

## Descrição

Este módulo adiciona funcionalidade de preenchimento automático de dados de produtos através da consulta ao Cadastro Centralizado de GTIN (CCG) da GS1 Brasil usando código GTIN/EAN.

## Funcionalidades

- **Campo de Busca GTIN/EAN**: Adiciona um campo na tela de cadastro de produtos para entrada de código de barras
- **Consulta Automática CCG**: Quando o GTIN é digitado completo (8, 12, 13 ou 14 dígitos), automaticamente consulta os dados no CCG
- **Autenticação com Certificado Digital**: Utiliza o certificado A1 configurado no módulo `l10n_br_certificate` para autenticação
- **Preenchimento Automático**: Preenche automaticamente os seguintes campos:
  - Código de Barras (barcode)
  - Nome/Descrição do Produto
  - NCM (Classificação Fiscal)
  - CEST (quando disponível)

## Sobre o GTIN e CCG

### GTIN (Global Trade Item Number)

O GTIN é um identificador internacional para produtos comerciais, anteriormente conhecido como código EAN. Pode ter 8, 12, 13 ou 14 dígitos e é usado principalmente em códigos de barras.

### CCG (Cadastro Centralizado de GTIN)

O CCG é mantido pela GS1 Brasil e contém informações básicas sobre produtos cadastrados pelos "donos de marca". Este cadastro é replicado para a SEFAZ e utilizado para validação de NFe/NFCe.

## Dependências

- `product`: Módulo padrão de produtos do Odoo
- `l10n_br_certificate`: Módulo de gerenciamento de certificados digitais A1

## Dependências Opcionais

Para aproveitar ao máximo o módulo, recomenda-se ter instalado:
- `l10n_br_fiscal`: Para campos NCM e CEST

## Configuração

### 1. Certificado Digital

Certifique-se de ter um certificado digital A1 válido configurado em:
- Menu: **Configurações > Certificados Digitais**
- O certificado deve estar no estado "Válido"
- Tipo: A1

### 2. Webservice CCG

O webservice utilizado é o **ccgConsGTIN** da SVRS (SEFAZ Virtual do Rio Grande do Sul):
- **URL Produção**: `https://dfe-servico.svrs.rs.gov.br/ws/ccgConsGTIN/ccgConsGTIN.asmx`
- **Protocolo**: SOAP 1.2
- **Autenticação**: Certificado Digital (mTLS)

## Uso

1. Acesse o menu de **Produtos** e crie um novo produto
2. No topo do formulário, você verá o campo **Buscar por GTIN/EAN**
3. Digite o código GTIN/EAN do produto (8, 12, 13 ou 14 dígitos)
4. Quando completar o código, a consulta será feita automaticamente
5. Os dados retornados pelo CCG preencherão os campos do formulário
6. Revise as informações e salve

## Validações

O módulo realiza as seguintes validações antes de consultar o CCG:

1. **Dígito Verificador**: Valida o dígito verificador do GTIN
2. **Prefixo GS1 Brasil**: Verifica se o GTIN possui prefixo 789 ou 790 (GS1 Brasil)
3. **Certificado Válido**: Verifica se existe certificado digital válido

## Códigos de Retorno do CCG

- **9490**: Consulta realizada com sucesso
- **9491**: GTIN com dígito verificador inválido
- **9492**: GTIN não possui prefixo 789 ou 790 (Brasil)
- **9493**: CNPJ/CPF do certificado não é emitente de NF-e ou NFC-e
- **9494**: GTIN inexistente no CCG
- **9495**: GTIN existe no CCG com situação inválida
- **9496**: GTIN existe, mas dono da marca não autorizou publicação
- **9497**: GTIN existe no CCG com NCM não informado
- **9498**: GTIN existe no CCG com NCM inválido

## Limitações

- **Apenas GS1 Brasil**: Este serviço só funciona para produtos registrados na GS1 Brasil (prefixos 789 e 790)
- **GTIN-8**: Para códigos GTIN-8, o prefixo GS1 está nas posições 7-9
- **GTIN-12/13/14**: Para códigos maiores, o prefixo GS1 está nas posições 2-4 (após normalização para 14 dígitos)
- **Consulta Síncrona**: A consulta é feita de forma síncrona no `onchange`, podendo causar delay de 2-5 segundos

## Estrutura Técnica

```
l10n_br_product_gtin_autocomplete/
├── __init__.py
├── __manifest__.py
├── README.md
├── models/
│   ├── __init__.py
│   └── product_template.py    # Lógica principal de consulta CCG
├── security/
│   └── ir.model.access.csv
└── views/
    └── product_template_views.xml
```

## Referências

- **Nota Técnica 2022.001**: Consulta GTIN via Web Service
- **Ajuste SINIEF 07/05**: Obrigatoriedade do campo cEAN
- **Ajuste SINIEF 19/16**: Validação do GTIN na NF-e/NFC-e

## Autor

Hiperpan

## Licença

LGPL-3
