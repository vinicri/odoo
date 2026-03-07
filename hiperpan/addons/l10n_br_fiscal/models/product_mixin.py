# Copyright (C) 2021  Renato Lima - Akretion <renato.lima@akretion.com.br>
# License AGPL-3 - See http://www.gnu.org/licenses/agpl-3.0.html

from odoo import api, models, fields, _


class ProductMixin(models.AbstractModel):
    _name = "l10n_br_fiscal.product.mixin"
    _description = "Fiscal Product Mixin"

    icms_origin_id = fields.Many2one(
        comodel_name="l10n_br_fiscal.icms.origin",
        string="ICMS Origin",
        required=True,
    )

    fiscal_type_id = fields.Many2one(
        comodel_name="l10n_br_fiscal.product.fiscal.type",
        string="Fiscal Type",
        required=True,
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

    def product_taxes_domain(self):
        return [("company_id", "=", self.env.company.id)]

    product_taxes_ids = fields.One2many(
        comodel_name="l10n_br_fiscal.product.taxes",
        inverse_name="product_tmpl_id",
        string="Product Taxes",
        domain=product_taxes_domain,
        copy=False,
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
            record.product_tmpl_taxes = record.product_taxes_ids.filtered(
                lambda t: t.company_id == self.env.company
            )[:1]

    product_taxes_icms_sn_tax_id = fields.Many2one(
        comodel_name="l10n_br_fiscal.tax",
        string="ICMS SN",
        related="product_tmpl_taxes.icms_sn_tax_id",
    )

    product_taxes_icms_sn_cst_nfe_code = fields.Char(
        string="Código CST ICMS SN",
        related="product_tmpl_taxes.icms_sn_cst_nfe_code",
    )

    product_taxes_icms_tax_id = fields.Many2one(
        comodel_name="l10n_br_fiscal.tax",
        string="ICMS",
        related="product_tmpl_taxes.icms_tax_id",
    )

    product_taxes_icms_cst_nfe_code = fields.Char(
        string="Código CST ICMS",
        related="product_tmpl_taxes.icms_cst_nfe_code",
    )

    product_taxes_has_icms_own_operation = fields.Boolean(
        string="Tributado em operação própria",
        related="product_tmpl_taxes.has_icms_own_operation",
    )

    product_taxes_is_deferment_cst = fields.Boolean(
        string="É CST de deferimento",
        related="product_tmpl_taxes.is_deferment_cst",
    )

    product_taxes_is_icms_with_base_reduction = fields.Boolean(
        string="É CST com redução de base de calculo",
        related="product_tmpl_taxes.is_icms_with_base_reduction",
    )

    product_taxes_icms_bc_modality = fields.Selection(
        string="Modalidade da Base de Calculo",
        related="product_tmpl_taxes.icms_bc_modality",
    )

    product_taxes_icms_bc_reduction_percent = fields.Float(
        string="Percentual de Redução da Base de Calculo",
        related="product_tmpl_taxes.icms_bc_reduction_percent",
    )

    product_taxes_icms_deferment_percent = fields.Float(
        string="Percentual de Deferimento",
        related="product_tmpl_taxes.icms_deferment_percent",
    )

    product_taxes_icms_tax_percent = fields.Float(
        string="Aliquota",
        related="product_tmpl_taxes.icms_tax_percent",
    )

    product_taxes_icms_fcp_tax_id = fields.Many2one(
        comodel_name="l10n_br_fiscal.tax",
        string="FCP",
        related="product_tmpl_taxes.icms_fcp_tax_id",
    )

    product_taxes_icms_fcp_tax_percent = fields.Float(
        string="Aliquota do FCP",
        related="product_tmpl_taxes.icms_fcp_tax_percent",
    )

    product_taxes_is_icms_st = fields.Boolean(
        string="É CST com ICMS ST",
        related="product_tmpl_taxes.is_icms_st",
    )

    product_taxes_icms_st_modality = fields.Selection(
        string="Modalidade da Base de Calculo",
        related="product_tmpl_taxes.icms_st_modality",
    )

    product_taxes_is_icms_st_mva_modality = fields.Boolean(
        string="É modalidade de base de calculo do ICMS ST MVA",
        related="product_tmpl_taxes.is_icms_st_mva_modality",
    )

    product_taxes_icms_st_mva_percent = fields.Float(
        string="Percentual de MVA",
        related="product_tmpl_taxes.icms_st_mva_percent",
    )

    product_taxes_icms_st_reduction_percent = fields.Float(
        string="Percentual de Redução da Base de Calculo",
        related="product_tmpl_taxes.icms_st_reduction_percent",
    )

    product_taxes_icms_st_tax_percent = fields.Float(
        string="Aliquota do ICMS ST",
        related="product_tmpl_taxes.icms_st_tax_percent",
    )

    product_taxes_icms_st_fcp_tax_id = fields.Many2one(
        comodel_name="l10n_br_fiscal.tax",
        string="FCP ST",
        related="product_tmpl_taxes.icms_st_fcp_tax_id",
    )

    product_taxes_icms_st_fcp_tax_percent = fields.Float(
        string="Aliquota do FCP ST",
        related="product_tmpl_taxes.icms_st_fcp_tax_percent",
    )

    product_taxes_pis_tax_id = fields.Many2one(
        comodel_name="l10n_br_fiscal.tax",
        string="PIS",
        related="product_tmpl_taxes.pis_tax_id",
    )

    product_taxes_cofins_tax_id = fields.Many2one(
        comodel_name="l10n_br_fiscal.tax",
        string="COFINS",
        related="product_tmpl_taxes.cofins_tax_id",
    )

    product_taxes_has_ipi = fields.Boolean(
        string="Tem IPI",
        related="product_tmpl_taxes.has_ipi",
    )

    product_taxes_is_ipi_with_percentage = fields.Boolean(
        string="É CST com Aliquota em Percentual",
        related="product_tmpl_taxes.is_ipi_with_percentage",
    )

    product_taxes_ipi_guideline_id = fields.Many2one(
        comodel_name="l10n_br_fiscal.ipi.guideline",
        string="Código de Enquadramento IPI",
        related="product_tmpl_taxes.ipi_guideline_id",
    )

    product_taxes_ipi_tax_id = fields.Many2one(
        comodel_name="l10n_br_fiscal.tax",
        string="IPI",
        related="product_tmpl_taxes.ipi_tax_id",
    )

    product_taxes_ipi_tax_percent = fields.Float(
        string="Aliquota",
        related="product_tmpl_taxes.ipi_tax_percent",
    )

    def _action_create_product_taxes(self, product_tmpl_id=None, product_id=None):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Novo Imposto do Produto"),
            "res_model": "l10n_br_fiscal.product.taxes",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_product_tmpl_id": product_tmpl_id,
                "default_product_id": product_id,
            },
        }

    def _action_edit_product_taxes(self, product_taxes_id):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Editar Imposto do Produto"),
            "res_model": "l10n_br_fiscal.product.taxes",
            "view_mode": "form",
            "res_id": product_taxes_id.id,
            "target": "new",
        }

    def action_delete_product_taxes(self):
        self.ensure_one()
        if self.product_tmpl_taxes:
            self.product_tmpl_taxes.unlink()
