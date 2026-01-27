from odoo import models, fields, api
from odoo.exceptions import ValidationError


class ResPartner(models.Model):
    _name = "res.partner"
    _inherit = "res.partner"

    nfe_document_email = fields.Char(string="Email para recepção da NF-e", size=60)

    is_card_processor = fields.Boolean(string="É processador de cartão", default=False)

    @api.constrains("is_card_processor")
    def _check_card_processor(self):
        for record in self:
            if record.is_card_processor:
                if not record.vat or len(record.vat) != 14:
                    raise ValidationError(
                        "O CNPJ do processador de cartão é obrigatório e deve ter 14 caracteres."
                    )

    is_marketplace_provider = fields.Boolean(
        string="É provedor de marketplace",
        default=False,
        help="Se o parceiro é um provedor de marketplace, o parceiro poderá ser utilizado na emissão de NF-e como intermediador.",
    )

    @api.constrains("is_marketplace_provider")
    def _check_marketplace_provider(self):
        for record in self:
            if record.is_marketplace_provider:
                if not record.vat or len(record.vat) != 14:
                    raise ValidationError(
                        "O CNPJ do provedor de marketplace é obrigatório e deve ter 14 caracteres."
                    )
