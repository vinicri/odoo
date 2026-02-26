from odoo import fields, models


class IpiGuideline(models.Model):
    _name = "l10n_br_fiscal.ipi.guideline"
    _inherit = "l10n_br_fiscal.data.abstract"
    _description = "IPI Guideline"

    code = fields.Char(required=True, index=True)

    name = fields.Char(required=True, index=True)

    def _domain_ipi_cst_in(self):
        return [
            (
                "tax_group_id",
                "=",
                self.env.ref("l10n_br_fiscal.tax_group_ipi").id,
            ),
            ("cst_type", "=", "in"),
        ]

    category = fields.Selection(
        string="Categoria",
        selection=[
            ("Imunidade", "Imunidade"),
            ("Suspensão", "Suspensão"),
            ("Isenção", "Isenção"),
            ("Redução", "Redução"),
            ("Outros", "Outros"),
        ],
    )

    ipi_cst_in = fields.Many2one(
        comodel_name="l10n_br_fiscal.cst",
        string="CST IPI In",
        domain=_domain_ipi_cst_in,
    )

    def _domain_ipi_cst_out(self):
        return [
            (
                "tax_group_id",
                "=",
                self.env.ref("l10n_br_fiscal.tax_group_ipi").id,
            ),
            ("cst_type", "=", "out"),
        ]

    ipi_cst_out = fields.Many2one(
        comodel_name="l10n_br_fiscal.cst",
        string="CST IPI Out",
        domain=_domain_ipi_cst_out,
    )

    _sql_constraints = [
        (
            "code_uniq",
            "unique (code)",
            "O código de enquadramento do IPI deve ser único",
        )
    ]
