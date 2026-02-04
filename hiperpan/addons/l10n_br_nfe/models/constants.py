NFE_OPERATION_TYPE = [("0", "Entrada"), ("1", "Saída")]

NFE_DOCUMENT_MODEL = [("55", "NF-e"), ("65", "NFC-e")]

# CFOPs válidos para NFC-e (modelo 65)
# Rejeição 794: NFC-e com CFOP inválido
NFCE_VALID_CFOPS = [
    "5101",  # Venda de produção do estabelecimento
    "5102",  # Venda de mercadoria de terceiros
    "5103",  # Venda de produção do estabelecimento efetuada fora do estabelecimento
    "5104",  # Venda de mercadoria adquirida ou recebida de terceiros, efetuada fora do estabelecimento
    "5115",  # Venda de mercadoria de terceiros, recebida anteriormente em consignação mercantil
    "5405",  # Venda de mercadoria de terceiros, sujeita a ST, como contribuinte substituído
    "5656",  # Venda de combustível ou lubrificante de terceiros, destinados a consumidor final
    "5667",  # Venda de combustível ou lubrificante a consumidor ou usuário final estabelecido em outra UF
    "5933",  # Prestação de serviço tributado pelo ISSQN (Nota Fiscal conjugada)
]

NFE_EMISSION_FINALITY = [
    ("1", "NF-e normal"),
    ("2", "NF-e complementar"),
    ("3", "NF-e de ajuste"),
    # obrigatorio referenciar a nota de entrada ou saida
    # (se o proprio vendedor estiver emitindo a nota de entrada pra devolucao)
    ("4", "Devolução de mercadoria"),
]

DESTINATION_ID = [
    ("1", "Operação interna"),
    ("2", "Operação interestadual"),
    ("3", "Operação com exterior"),
]
