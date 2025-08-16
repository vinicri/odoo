from odoo import models, fields, api


ENV_EMISSION = [("0", "Produção"), ("1", "Homologação")]


class Company(models.Model):
    _name = "res.company"
    _inherit = ["res.company", "l10n_br_fiscal.party.mixin"]

    fiscal_document_emission_env = fields.Selection(
        ENV_EMISSION,
        string="Ambiente de Emissão de Documentos Fiscais",
        required=True,
        tracking=True,
        default="1",
    )
