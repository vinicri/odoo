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
        string="Allowed IPI CSTs",
        compute="_compute_allowed_ipi_tax_ids",
    )

    # filtra os impostos de IPI associados ao CST de saída do código de enquadramento
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

    allowed_pis_tax_ids = fields.Many2many(
        comodel_name="l10n_br_fiscal.tax",
        string="Allowed PIS CSTs",
        compute="_compute_allowed_pis_tax_ids",
    )

    @api.depends("cofins_tax_id")
    def _compute_allowed_pis_tax_ids(self):
        for record in self:
            if record.cofins_tax_id:
                record.allowed_pis_tax_ids = self.env["l10n_br_fiscal.tax"].search(
                    [
                        (
                            "tax_group_id",
                            "=",
                            self.env.ref("l10n_br_fiscal.tax_group_pis").id,
                        ),
                        ("cst_out_id", "=", record.cofins_tax_id.cst_out_id.id),
                        (
                            ("id", "!=", self.env.ref("l10n_br_fiscal.tax_pis_1_65").id)
                            if self.env.company.regular_framework_type == "LP"
                            else ()
                        ),
                    ]
                )
            elif self.env.company.regular_framework_type == "LP":
                record.allowed_pis_tax_ids = self.env["l10n_br_fiscal.tax"].search(
                    [
                        (
                            "tax_group_id",
                            "=",
                            self.env.ref("l10n_br_fiscal.tax_group_pis").id,
                        ),
                        ("id", "!=", self.env.ref("l10n_br_fiscal.tax_pis_1_65").id),
                    ]
                )
            elif self.env.company.regular_framework_type == "LR":
                record.allowed_pis_tax_ids = self.env["l10n_br_fiscal.tax"].search(
                    [
                        (
                            "tax_group_id",
                            "=",
                            self.env.ref("l10n_br_fiscal.tax_group_pis").id,
                        )
                    ]
                )
            else:
                record.allowed_pis_tax_ids = False

    pis_tax_id = fields.Many2one(
        comodel_name="l10n_br_fiscal.tax",
        string="PIS",
        domain="[('id', 'in', allowed_pis_tax_ids)]",
        company_dependent=True,
    )

    allowed_cofins_tax_ids = fields.Many2many(
        comodel_name="l10n_br_fiscal.tax",
        string="Allowed COFINS Tax",
        compute="_compute_allowed_cofins_tax_ids",
    )

    @api.depends("pis_tax_id")
    def _compute_allowed_cofins_tax_ids(self):
        for record in self:
            if record.pis_tax_id:
                record.allowed_cofins_tax_ids = self.env["l10n_br_fiscal.tax"].search(
                    [
                        (
                            "tax_group_id",
                            "=",
                            self.env.ref("l10n_br_fiscal.tax_group_cofins").id,
                        ),
                        ("cst_out_id", "=", record.pis_tax_id.cst_out_id.id),
                        (
                            (
                                "id",
                                "!=",
                                self.env.ref("l10n_br_fiscal.tax_cofins_7_6").id,
                            )
                            if self.env.company.regular_framework_type == "LP"
                            else ()
                        ),
                    ]
                )
            elif self.env.company.regular_framework_type == "LP":
                record.allowed_cofins_tax_ids = self.env["l10n_br_fiscal.tax"].search(
                    [
                        (
                            "tax_group_id",
                            "=",
                            self.env.ref("l10n_br_fiscal.tax_group_cofins").id,
                        ),
                        ("id", "!=", self.env.ref("l10n_br_fiscal.tax_cofins_7_6").id),
                    ]
                )
            elif self.env.company.regular_framework_type == "LR":
                record.allowed_cofins_tax_ids = self.env["l10n_br_fiscal.tax"].search(
                    [
                        (
                            "tax_group_id",
                            "=",
                            self.env.ref("l10n_br_fiscal.tax_group_cofins").id,
                        )
                    ]
                )
            else:
                record.allowed_cofins_tax_ids = False

    cofins_tax_id = fields.Many2one(
        comodel_name="l10n_br_fiscal.tax",
        string="COFINS",
        domain="[('id', 'in', allowed_cofins_tax_ids)]",
        company_dependent=True,
    )

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
