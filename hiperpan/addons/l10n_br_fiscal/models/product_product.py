# Copyright (C) 2021  Renato Lima - Akretion <renato.lima@akretion.com.br>
# License AGPL-3 - See http://www.gnu.org/licenses/agpl-3.0.html

from odoo import models, api, fields


class ProductProduct(models.Model):
    _name = "product.product"
    _inherit = ["product.product", "l10n_br_fiscal.product.mixin"]

    default_code = fields.Integer("Internal Reference", index=True)
