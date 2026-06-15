from odoo import _, models, fields, api
from odoo.exceptions import ValidationError


TAX_FRAMEWORK = [
    ("1", "1 - Simples Nacional"),
    ("2", "2 - Simples Nacional – excesso de sublimite da receita bruta"),
    ("3", "3 - Regime Normal"),
]

REGULAR_FRAMEWORK_TYPE = [
    ("LR", "Lucro Real"),
    ("LP", "Lucro Presumido"),
]


class PartyMixin(models.AbstractModel):
    _name = "l10n_br_fiscal.party.mixin"
    _description = "Party Mixin"

    fiscal_framework = fields.Selection(
        string="Fiscal Framework",
        selection=TAX_FRAMEWORK,
        tracking=True,
        help="Fiscal Framework of the company.",
    )

    regular_framework_type = fields.Selection(
        string="Regular Framework Type",
        selection=REGULAR_FRAMEWORK_TYPE,
        tracking=True,
        help="Tipo de regime normal",
    )

    # adicionar o motivo de ter este campo
    # acredito que seja pra saber se na devolucao o ipi deve ser destacado ?
    # isso eh pra saber se a empresa contribui com IPI no simples e
    # deve colocar o ipi cst 99 na nfe pra produtos de produção propria
    ipi_contributes = fields.Boolean(
        string="Contribui com IPI",
        default=False,
        help="Empresa contribui com IPI no Simples ou Regime Normal.",
    )

    main_cnae_id = fields.Many2one(
        comodel_name="l10n_br_fiscal.cnae",
        string="CNAE Principal",
        help="CNAE Principal da empresa.",
    )
