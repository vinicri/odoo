# Brazilian Partner NFe Autocomplete

## Descrição

Este módulo adiciona funcionalidade de preenchimento automático de dados de parceiros (clientes/fornecedores) através da consulta ao cadastro da SEFAZ usando CNPJ ou CPF.

## Funcionalidades

- **Campo CNPJ/CPF**: Adiciona um campo na tela de cadastro de parceiros para entrada de CNPJ (14 dígitos) ou CPF (11 dígitos)
- **Consulta Automática**: Quando o número está completo, automaticamente consulta os dados cadastrais na SEFAZ
- **Autenticação com Certificado Digital**: Utiliza o certificado A1 configurado no módulo `l10n_br_certificate` para autenticação
- **Preenchimento Automático**: Preenche automaticamente os seguintes campos:
  - Nome/Razão Social
  - CNPJ/CPF (campo `vat`)
  - Tipo de empresa (Pessoa Jurídica/Física)
  - Inscrição Estadual
  - Endereço completo (logradouro, número, complemento)
  - Bairro/Distrito
  - Cidade (através do código IBGE)
  - Estado
  - CEP

## Dependências

- `l10n_br_nfe`: Módulo de NFe com configuração de endpoints SEFAZ
- `l10n_br_certificate`: Módulo de gerenciamento de certificados digitais A1

## Configuração

### 1. Certificado Digital

Certifique-se de ter um certificado digital A1 válido configurado em:
- Menu: **Configurações > Certificados Digitais**
- O certificado deve estar no estado "Válido"
- Tipo: A1

### 2. Ambiente de Emissão

Configure o ambiente (Produção/Homologação) em:
- Menu: **Configurações > Empresas > [Sua Empresa]**
- Campo: **Ambiente de Emissão de Documentos Fiscais**

### 3. Endpoints SEFAZ

Os endpoints para consulta estão configurados em `l10n_br_nfe/utils/endpoints.py`. Atualmente suporta:
- **MG (Minas Gerais)**: Produção e Homologação

Para adicionar outros estados, edite o arquivo de endpoints.

## Uso

1. Acesse o menu de **Contatos** e crie um novo parceiro
2. No topo do formulário, você verá o campo **CNPJ/CPF**
3. Digite o CNPJ (14 dígitos) ou CPF (11 dígitos)
4. Quando completar o número, a consulta será feita automaticamente
5. Os dados retornados pela SEFAZ preencherão os campos do formulário
6. Revise as informações e salve

## Campos Adicionados

### res.partner
- `l10n_br_cnpj_cpf`: Campo para entrada de CNPJ/CPF
- `l10n_br_district`: Bairro/Distrito do endereço

### res.city
- `l10n_br_ibge_code`: Código IBGE do município (7 dígitos)

## Serviço SEFAZ Utilizado

- **Serviço**: NfeConsultaCadastro (CadConsultaCadastro4)
- **Versão**: 2.00
- **Protocolo**: SOAP 1.2
- **Autenticação**: Certificado Digital (mTLS)

## Avisos e Observações

- A consulta só funciona para CNPJ/CPF que estejam ativos no cadastro da SEFAZ
- É necessário conexão com internet para realizar a consulta
- A consulta é feita de forma síncrona no evento `onchange` do campo
- Se o parceiro já tiver dados cadastrados, um aviso será exibido antes de sobrescrever

## Estrutura Técnica

```
l10n_br_partner_nfe_autocomplete/
├── __init__.py
├── __manifest__.py
├── README.md
├── models/
│   ├── __init__.py
│   ├── res_partner.py    # Lógica principal de consulta SEFAZ
│   └── res_city.py        # Extensão com código IBGE
├── security/
│   └── ir.model.access.csv
└── views/
    └── res_partner_views.xml
```

## Autor

Hiperpan

## Licença

LGPL-3
