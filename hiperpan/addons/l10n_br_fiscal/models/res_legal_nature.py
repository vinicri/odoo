from odoo import fields, models

# not being used
class LegalNature(models.Model):
    _name = "l10n_br_fiscal.legal.nature"
    _inherit = "l10n_br_fiscal.data.abstract"
    _description = "Legal Nature"

    code = fields.Char(size=5)

    _sql_constraints = [
        (
            "fiscal_legal_nature_code_uniq",
            "unique (code)",
            "Legal Nature already exists with this code !",
        )
    ]
