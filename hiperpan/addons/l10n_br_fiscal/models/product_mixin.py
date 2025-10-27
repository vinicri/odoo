# Copyright (C) 2021  Renato Lima - Akretion <renato.lima@akretion.com.br>
# License AGPL-3 - See http://www.gnu.org/licenses/agpl-3.0.html

from odoo import api, models, fields, _
from odoo.exceptions import ValidationError


from ..constants.fiscal import (
    NCM_FOR_SERVICE_REF,
    PRODUCT_FISCAL_TYPE_SERVICE,
    TAX_DOMAIN_ICMS,
    TAX_DOMAIN_ISSQN,
)


class ProductMixin(models.AbstractModel):
    _name = "l10n_br_fiscal.product.mixin"
    _description = "Fiscal Product Mixin"

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

    def _extract_fiscal_genre_id(self, record):
        if record.ncm_id:
            record.fiscal_genre_id = self.env["l10n_br_fiscal.ncm.genre"].search(
                [("code", "=", record.ncm_id.code[0:2])]
            )
        else:
            record.fiscal_genre_id = False

    # @api.depends("fiscal_type")
    # def _compute_tax_icms_or_issqn(self):
    #     for product in self:
    #         if product.fiscal_type == PRODUCT_FISCAL_TYPE_SERVICE:
    #             product.tax_icms_or_issqn = TAX_DOMAIN_ISSQN
    #         else:
    #             product.tax_icms_or_issqn = TAX_DOMAIN_ICMS
