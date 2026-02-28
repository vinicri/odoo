# Copyright (C) 2019  Renato Lima - Akretion <renato.lima@akretion.com.br>
# License AGPL-3 - See http://www.gnu.org/licenses/agpl-3.0.html

from odoo import _, fields, models


class TaxDomain(models.Model):
    _name = "l10n_br_fiscal.tax.domain"
    _description = "Tax Domain"
    _order = "name"

    name = fields.Char(required=True)
    code = fields.Char(required=True)

    _sql_constraints = [
        (
            "l10n_br_fiscal_tax_domain_code_uniq",
            "unique (code)",
            _("Tax Domain already exists with this code!"),
        )
    ]
