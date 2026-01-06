from odoo import fields, models


class IcmsDesonReason(models.Model):
    _name = "l10n_br_fiscal.icms.deson.reason"
    _inherit = "l10n_br_fiscal.data.abstract"
    _order = "code"
    _description = "Motivo da Desoneração do ICMS"

    cst_ids = fields.Many2many(
        comodel_name="l10n_br_fiscal.cst",
        relation="l10n_br_fiscal_icms_deson_reason_cst_rel",
        column1="icms_deson_reason_id",
        column2="cst_id",
        string="CSTs Permitidos",
        domain=[("tax_domain", "=", "icms")],
        help="CSTs ICMS que permitem este motivo de desoneração",
    )

    _sql_constraints = [
        ("code_uniq", "unique (code)", "Code must be unique"),
    ]
