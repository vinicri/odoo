NFE_OPERATION_TYPE = [("0", "Entrada"), ("1", "Saída")]

NFE_DOCUMENT_MODEL = [("55", "NF-e"), ("65", "NFC-e")]

NFE_EMISSION_FINALITY = [
    ("1", "NF-e normal"),
    ("2", "NF-e complementar"),
    ("3", "NF-e de ajuste"),
    # obrigatorio referenciar a nota de entrada ou saida
    # (se o proprio vendedor estiver emitindo a nota de entrada pra devolucao)
    ("4", "Devolução de mercadoria"),
]
