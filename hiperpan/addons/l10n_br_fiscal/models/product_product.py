# Copyright (C) 2021  Renato Lima - Akretion <renato.lima@akretion.com.br>
# License AGPL-3 - See http://www.gnu.org/licenses/agpl-3.0.html

from odoo import models, api, fields, _
from odoo.exceptions import ValidationError
from odoo.osv import expression


class ProductProduct(models.Model):
    _name = "product.product"
    _inherit = ["product.product", "l10n_br_fiscal.product.mixin"]

    default_code = fields.Integer("Internal Reference", index=True)

    @api.model
    def name_search(self, name="", args=None, operator="ilike", limit=100):
        """product.product.name_search (core) unconditionally tries an exact
        match on default_code (e.g. `[('default_code', '=', name)]`) for any
        non-empty search term. Since default_code is overridden to Integer on
        this model, a non-numeric search term (e.g. typing a product
        description) makes that comparison raise a ValueError deep inside SQL
        param binding instead of just finding no match — crashing the whole
        search instead of falling through to the name/barcode lookup.

        A non-numeric name can never match an Integer default_code anyway, so
        for that case this searches by name/barcode directly instead of
        delegating to core (which cannot be asked to skip that domain leg).
        """
        if name and not name.lstrip("-").isdigit():
            is_positive = operator not in expression.NEGATIVE_TERM_OPERATORS
            if is_positive:
                # matches either field, mirroring core's ilike-on-name-or-code
                name_domain = expression.OR(
                    [[("name", operator, name)], [("barcode", operator, name)]]
                )
            else:
                # "not ilike" must exclude products matching on either field,
                # so the negated legs are ANDed rather than ORed
                name_domain = expression.AND(
                    [[("name", operator, name)], [("barcode", operator, name)]]
                )
            domain = expression.AND([args or [], name_domain])
            products = self.search_fetch(domain, ["display_name"], limit=limit)
            return [(product.id, product.display_name) for product in products]
        return super().name_search(name, args, operator, limit)

    ncm_id = fields.Many2one(
        comodel_name="l10n_br_fiscal.ncm",
        string="NCM",
        required=True,
    )

    cest_id = fields.Many2one(
        comodel_name="l10n_br_fiscal.cest",
        string="CEST",
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

    product_taxes_ids = fields.One2many(
        inverse_name="product_id",
    )

    product_tmpl_taxes = fields.Many2one(
        comodel_name="l10n_br_fiscal.product.taxes",
        string="Product Taxes (Company)",
        compute="_compute_product_tmpl_taxes",
    )

    @api.depends("product_taxes_ids.company_id")
    @api.depends_context("company")
    def _compute_product_tmpl_taxes(self):
        for record in self:
            taxes = record.product_taxes_ids.filtered(
                lambda t: t.company_id == self.env.company
            )[:1]
            if taxes:
                record.product_tmpl_taxes = taxes
            else:
                record.product_tmpl_taxes = record.product_tmpl_id.product_tmpl_taxes

    has_own_taxes = fields.Boolean(
        string="Tem imposto próprio",
        compute="_compute_has_own_taxes",
    )

    @api.depends("product_tmpl_taxes")
    def _compute_has_own_taxes(self):
        for record in self:
            record.has_own_taxes = (
                record.product_tmpl_taxes != record.product_tmpl_id.product_tmpl_taxes
            )

    def action_create_product_taxes(self):
        return self._action_create_product_taxes(product_id=self.id)

    def action_edit_product_taxes(self):
        return self._action_edit_product_taxes(self.product_tmpl_taxes)

    @api.model_create_multi
    def create(self, vals_list):
        next_number = self._get_next_sequence_code()
        """Override create to set sequential default_code if not provided"""
        for vals in vals_list:
            if not vals.get("default_code"):
                vals["default_code"] = next_number
                next_number += 1

        return super().create(vals_list)

    @api.model
    def _get_next_sequence_code(self):
        """Get next sequential code for product"""

        # Get the highest existing numeric default_code
        last_product = self.search(
            [
                ("default_code", "!=", False),
            ],
            order="default_code desc",
            limit=1,
        )

        if last_product and last_product.default_code:
            try:
                # Extract number from last code and increment
                last_number = int(last_product.default_code)
                next_number = last_number + 1
            except (ValueError, IndexError):
                next_number = 1
        else:
            next_number = 1

        return next_number  # Simple numeric: 1, 2, 3, etc.
