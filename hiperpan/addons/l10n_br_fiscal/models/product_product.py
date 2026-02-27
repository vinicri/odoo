# Copyright (C) 2021  Renato Lima - Akretion <renato.lima@akretion.com.br>
# License AGPL-3 - See http://www.gnu.org/licenses/agpl-3.0.html

import re
from odoo import models, api, fields


class ProductProduct(models.Model):
    _name = "product.product"
    _inherit = ["product.product", "l10n_br_fiscal.product.mixin"]

    default_code = fields.Integer("Internal Reference", index=True)

    no_barcode = fields.Boolean(
        "Não possui código de barras",
        default=False,
    )

    ncm_id = fields.Many2one(
        comodel_name="l10n_br_fiscal.ncm",
        string="NCM",
        required=True,
    )

    cest_id = fields.Many2one(
        comodel_name="l10n_br_fiscal.cest",
        string="CEST",
    )

    icms_origin_id = fields.Many2one(
        comodel_name="l10n_br_fiscal.icms.origin",
        string="ICMS Origin",
        required=True,
    )

    fiscal_genre_id = fields.Many2one(
        comodel_name="l10n_br_fiscal.ncm.genre",
        string="Fiscal NCM Genre",
        compute="_compute_fiscal_genre_id",
        store=True,
        required=True,
        readonly=True,
    )

    @api.depends("ncm_id")
    def _compute_fiscal_genre_id(self):
        for record in self:
            self._extract_fiscal_genre_id(record)

    fiscal_additional_information = fields.Text(
        string="Informações adicionais de produto para documento fiscal"
    )

    mrp_bom_id = fields.Many2one(
        comodel_name="mrp.bom",
        string="Recipe",
        domain="[('product_id', '=', id), ('product_tmpl_id', '=', product_tmpl_id)]",
    )
