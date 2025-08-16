from odoo import models, fields, api


TAX_FRAMEWORK = [
    ("1", "1 - Simples Nacional"),
    ("2", "2 - Simples Nacional – excesso de sublimite da receita bruta"),
    ("3", "3 - Regime Normal"),
]


class PartyMixin(models.AbstractModel):
    _name = "l10n_br_fiscal.party.mixin"
    _description = "Party Mixin"

    fiscal_framework = fields.Selection(
        string="Fiscal Framework",
        selection=TAX_FRAMEWORK,
        default="3",
        required=True,
        tracking=True,
        help="Fiscal Framework of the company.",
    )

    ipi_contributes = fields.Boolean(
        string="Contribui com IPI",
        default=False,
        help="Empresa contribui com IPI no Simples ou Regime Normal.",
    )
