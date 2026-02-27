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

    fiscal_type_id = fields.Many2one(
        comodel_name="l10n_br_fiscal.product.fiscal.type",
        string="Fiscal Type",
        required=True,
    )

    has_ipi = fields.Boolean(
        string="Tem IPI",
        compute="_compute_has_ipi",
        readonly=True,
    )

    @api.depends("fiscal_type_id")
    def _compute_has_ipi(self):
        for record in self:
            record.has_ipi = record.fiscal_type_id.code == "04"

    @api.onchange("fiscal_type_id")
    def _onchange_fiscal_type_reset_ipi(self):
        for record in self:
            if record.has_ipi:
                if not record.ipi_guideline_id:
                    record.ipi_guideline_id = self.env.ref(
                        "l10n_br_fiscal.ipi_guideline_999"
                    )
            else:
                record.ipi_guideline_id = False
                record.ipi_tax_id = False

    ipi_guideline_id = fields.Many2one(
        comodel_name="l10n_br_fiscal.ipi.guideline",
        string="Código de Enquadramento",
        default=lambda self: self.env.ref("l10n_br_fiscal.ipi_guideline_999"),
    )

    allowed_ipi_tax_ids = fields.Many2many(
        comodel_name="l10n_br_fiscal.tax",
        string="Allowed CSTs",
        compute="_compute_allowed_ipi_tax_ids",
    )

    @api.depends(
        "ipi_guideline_id",
        "ipi_guideline_id.ipi_cst_out",
    )
    def _compute_allowed_ipi_tax_ids(self):
        ipi_group = self.env.ref("l10n_br_fiscal.tax_group_ipi")
        for record in self:
            if record.ipi_guideline_id.ipi_cst_out:
                record.allowed_ipi_tax_ids = self.env["l10n_br_fiscal.tax"].search(
                    [
                        ("tax_group_id", "=", ipi_group.id),
                        ("cst_out_id", "=", record.ipi_guideline_id.ipi_cst_out.id),
                    ]
                )
            else:
                record.allowed_ipi_tax_ids = self.env["l10n_br_fiscal.tax"].search(
                    [("tax_group_id", "=", ipi_group.id)]
                )

    ipi_tax_id = fields.Many2one(
        comodel_name="l10n_br_fiscal.tax",
        string="IPI",
        domain="[('id', 'in', allowed_ipi_tax_ids)]",
    )

    @api.onchange("ipi_guideline_id")
    def _onchange_ipi_guideline_id(self):
        for record in self:
            record.ipi_tax_id = False

    is_ipi_qtt = fields.Boolean(
        string="IPI Tributado por Unidade",
        compute="_compute_is_ipi_qtt",
        readonly=True,
    )

    @api.depends("ipi_tax_id")
    def _compute_is_ipi_qtt(self):
        for record in self:
            record.is_ipi_qtt = record.ipi_tax_id == self.env.ref(
                "l10n_br_fiscal.tax_ipi_qtt"
            )

    ipi_cst_id = fields.Many2one(
        related="ipi_tax_id.cst_out_id",
        string="CST IPI",
        readonly=True,
    )

    is_ipi_with_percentage = fields.Boolean(
        string="É CST com Aliquota em Percentual",
        compute="_compute_is_ipi_with_percentage",
        readonly=True,
    )

    @api.depends("ipi_cst_id")
    def _compute_is_ipi_with_percentage(self):
        for record in self:
            record.is_ipi_with_percentage = record.ipi_cst_id.code in (
                "00",
                "50",
                "49",
                "99",
            )

    ipi_tax_percent = fields.Float(
        related="ipi_tax_id.percent_amount",
        string="Aliquota",
        digits=(3, 4),
        readonly=True,
        store=True,
    )

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
