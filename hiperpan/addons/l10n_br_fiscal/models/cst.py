# Copyright (C) 2018  Renato Lima - Akretion
# License AGPL-3 - See http://www.gnu.org/licenses/agpl-3.0.html

from odoo import _, fields, models

from ..constants.fiscal import FISCAL_IN_OUT_ALL


class CST(models.Model):
    _name = "l10n_br_fiscal.cst"
    _inherit = "l10n_br_fiscal.data.abstract"
    _order = "tax_domain_id, code"
    _description = "CST"

    code = fields.Char(size=4)

    cst_type = fields.Selection(
        selection=FISCAL_IN_OUT_ALL, string="Type", required=True
    )

    tax_domain_id = fields.Many2one(
        comodel_name="l10n_br_fiscal.tax.domain",
        string="Tax Domain",
        required=True,
    )

    _sql_constraints = [
        (
            "l10n_br_fiscal_cst_code_tax_domain_uniq",
            "unique (code, tax_domain_id)",
            _("CST already exists with this code and tax domain !"),
        )
    ]
