# Copyright (C) 2021  Renato Lima - Akretion <renato.lima@akretion.com.br>
# License AGPL-3 - See http://www.gnu.org/licenses/agpl-3.0.html

from odoo import api, models

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

        print(last_product)

        if last_product and last_product.default_code:
            try:
                # Extract number from last code and increment
                last_number = int(last_product.default_code)
                next_number = last_number + 1
                print("entrou no try")
                print(next_number)
            except (ValueError, IndexError):
                next_number = 1
                print("entrou no else")
                print(next_number)
        else:
            print("entrou no else 2")
            next_number = 1

        return next_number  # Simple numeric: 1, 2, 3, etc.

    @api.depends("fiscal_type_id", "fiscal_genre_id")
    def _compute_ncm_id(self):
        for product in self:
            if product.fiscal_type_id.code == "09":  # service
                product.ncm_id = self.env.ref(NCM_FOR_SERVICE_REF)
            # elif product.fiscal_genre_id and product.ncm_id:
            #     if product.fiscal_genre_id.code != product.ncm_id.code[0:2]:
            #         product.ncm_id = False
            elif product.ncm_id is None:
                product.ncm_id = False

    @api.depends("ncm_id")
    def _compute_fiscal_genre_id(self):
        for product in self:
            if product.ncm_id:
                product.fiscal_genre_id = self.env["l10n_br_fiscal.ncm.genre"].search(
                    [("code", "=", product.ncm_id.code[0:2])]
                )
            elif product.fiscal_genre_id is None:
                product.fiscal_genre_id = False

    # @api.depends("fiscal_type")
    # def _compute_tax_icms_or_issqn(self):
    #     for product in self:
    #         if product.fiscal_type == PRODUCT_FISCAL_TYPE_SERVICE:
    #             product.tax_icms_or_issqn = TAX_DOMAIN_ISSQN
    #         else:
    #             product.tax_icms_or_issqn = TAX_DOMAIN_ICMS
