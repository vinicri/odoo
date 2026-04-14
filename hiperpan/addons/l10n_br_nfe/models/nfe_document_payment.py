from odoo import models, fields, api
from odoo.exceptions import ValidationError

PAYMENT_TYPE = [
    ("0", "À vista"),
    ("1", "À prazo"),
]

PAYMENT_METHOD = [
    ("01", "Dinheiro"),
    ("02", "Cheque"),
    ("03", "Cartão de Crédito"),
    ("04", "Cartão de Débito"),
    ("05", "Cartão de Crédito da Loja, Crediário"),
    ("10", "Vale Alimentação"),
    ("11", "Vale Refeição"),
    ("12", "Vale Presente"),
    ("13", "Vale Combustível"),
    ("15", "Boleto Bancário"),
    ("16", "Depósito Bancário"),
    ("17", "PIX Dinâmico"),
    ("18", "Transferência bancária, Carteira Digital"),
    ("19", "Programa de fidelidade, Cashback, Crédito Virtual"),
    ("20", "PIX Estático"),
    ("21", "Crédito em Loja"),
    ("22", "Pagamento eletrônico não informado, falha do sistema emissor"),
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
        "1",
        "Pagamento integrado com o sistema de automação da empresa (Ex.: equipamento TEF, Comércio Eletrônico)",
    ),
    (
        "2",
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
    )

    # opcional.
    change_value = fields.Float(string="Valor do Troco", digits=(13, 2))

    @api.constrains("change_value")
    def _check_change_value(self):
        for record in self:
            if record.change_value and record.change_value > record.payment_value:
                raise ValidationError(
                    "O Valor do Troco não pode ser maior que o Valor do Pagamento."
                )

    is_card_payment = fields.Boolean(
        string="É pagamento com cartão", compute="_compute_is_card_payment"
    )

    @api.depends("payment_method")
    def _compute_is_card_payment(self):
        for record in self:
            record.is_card_payment = record.payment_method in ["03", "04"]

    # Valor do Pagamento.

    # @api.depends("nfe_id")
    # def _compute_payment_value(self):
    #     for record in self:
    #         if record.payment_value:
    #             continue
    #         all_nfe_payments = self.env["l10n_br_nfe.nfe.document.payment"].search(
    #             [("nfe_id", "=", self.nfe_id.id)]
    #         )
    #         total_payment_value = sum(all_nfe_payments.mapped("payment_value"))
    #         remaining_payment_value = record.nfe_id.total_nfe - total_payment_value
    #         if remaining_payment_value > 0:
    #             record.payment_value = remaining_payment_value
    #         else:
    #             record.payment_value = 0

    # grupo de cartoes. opcional
    card_integration_type = fields.Selection(
        string="Tipo de Integração do Cartão",
        selection=CARD_INTEGRATION_TYPE,
    )

    card_processor_id = fields.Many2one(
        comodel_name="res.partner",
        string="Processador de Cartão",
        domain="[('is_company', '=', True), ('is_card_processor', '=', True)]",
    )

    # CNPJ do Processador de Cartão. opcional
    card_processor_cnpj = fields.Char(
        related="card_processor_id.vat",
        string="CNPJ do Processador de Cartão",
        store=True,
        size=14,
        readonly=True,
    )

    @api.constrains("card_processor_id")
    def _check_card_processor_id(self):
        for record in self:
            if record.card_processor_id and not record.card_processor_cnpj:
                raise ValidationError("O CNPJ do Processador de Cartão é obrigatório.")

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

    @api.constrains("is_card_payment", "card_integration_type")
    def _check_is_card_payment(self):
        for record in self:
            if record.is_card_payment:
                if not record.card_integration_type:
                    raise ValidationError(
                        "O Tipo de Integração do Cartão é obrigatório."
                    )
