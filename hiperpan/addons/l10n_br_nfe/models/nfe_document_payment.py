from odoo import models, fields, api

PAYMENT_TYPE = [
    ("0", "À vista"),
    ("1", "À prazo"),
]

PAYMENT_METHOD = [
    ("01", "Dinheiro"),
    ("02", "Cheque"),
    ("03", "Cartão de Crédito"),
    ("04", "Cartão de Débito"),
    ("05", "Crédito Loja"),
    ("10", "Vale Alimentação"),
    ("11", "Vale Refeição"),
    ("12", "Vale Presente"),
    ("13", "Vale Combustível"),
    ("15", "Boleto Bancário"),
    ("16", "Depósito Bancário"),
    ("17", "Pagamento Instantâneo (PIX)"),
    ("18", "Transferência bancária, Carteira Digital"),
    ("19", "Programa de fidelidade, Cashback, Crédito Virtual"),
    (
        "90",
        "Sem pagamento",
    ),  # Obrigatório para NF-e/NFC-e de Ajuste ou Devolução  (verificar se procede)
    (
        "99",
        "Outros",
    ),  # Rejeitado para NFC-e a partir de 01/02/2021 (verificar se procede)
]

CARD_INTEGRATION_TYPE = [
    (
        "01",
        "Pagamento integrado com o sistema de automação da empresa (Ex.: equipamento TEF, Comércio Eletrônico)",
    ),
    (
        "02",
        "Pagamento não integrado com o sistema de automação da empresa (Ex.: equipamento POS)",
    ),
]

CARD_BRAND = [
    ("01", "Visa"),
    ("02", "Mastercard"),
    ("03", "American Express"),
    ("04", "Sorocred"),
    ("05", "Diners Club"),
    ("06", "Elo"),
    ("07", "Hipercard"),
    ("08", "Aura"),
    ("09", "Cabal"),
    ("99", "Outros"),
]


class NFeDocumentPayment(models.Model):
    _name = "l10n_br_nfe.nfe.document.payment"
    _description = "Pagamentos da NF-e"

    nfe_id = fields.Many2one(
        comodel_name="l10n_br_nfe.nfe.document",
        string="NF-e",
        required=True,
        ondelete="cascade",
    )

    type = fields.Selection(
        string="Tipo de Pagamento",
        selection=PAYMENT_TYPE,
        default="0",
        required=True,
    )

    payment_method = fields.Selection(
        string="Método de Pagamento",
        selection=PAYMENT_METHOD,
        required=True,
    )

    payment_value = fields.Float(
        string="Valor do Pagamento",
        digits=(13, 2),
        required=True,
        compute="_compute_payment_value",
        store=True,
    )
    # Valor do Pagamento.

    @api.depends("nfe_id")
    def _compute_payment_value(self):
        for record in self:
            if record.payment_value:
                continue
            all_nfe_payments = self.env["l10n_br_nfe.nfe.document.payment"].search(
                [("nfe_id", "=", self.nfe_id.id)]
            )
            total_payment_value = sum(all_nfe_payments.mapped("payment_value"))
            remaining_payment_value = record.nfe_id.total_nfe - total_payment_value
            if remaining_payment_value > 0:
                record.payment_value = remaining_payment_value
            else:
                record.payment_value = 0

    # grupo de cartoes. opcional
    card_integration_type = fields.Selection(
        string="Tipo de Integração do Cartão",
        selection=CARD_INTEGRATION_TYPE,
    )

    card_processor_cnpj = fields.Char(string="CNPJ do Processador de Cartão", size=14)
    # CNPJ do Processador de Cartão. opcional

    # opcional
    card_brand = fields.Selection(
        string="Bandeira do Cartão",
        selection=CARD_BRAND,
    )

    # opcional
    card_authorization_number = fields.Char(
        string="Número de Autorização do Cartão", size=20
    )
    # Número de Autorização da Transação

    # opcional.
    change_value = fields.Float(string="Valor do Troco", digits=(13, 2))
