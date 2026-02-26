# Copyright (C) 2013  Renato Lima - Akretion <renato.lima@akretion.com.br>
# License AGPL-3 - See http://www.gnu.org/licenses/agpl-3.0.html

from odoo import fields, models, api, _
from odoo.exceptions import ValidationError

from ..constants.fiscal import (
    NCM_FOR_SERVICE_REF,
    PRODUCT_FISCAL_TYPE,
    PRODUCT_FISCAL_TYPE_SERVICE,
    TAX_DOMAIN_ICMS,
    TAX_ICMS_OR_ISSQN,
)
from ..constants.icms import ICMS_ORIGIN, ICMS_ORIGIN_DEFAULT


class ProductTemplate(models.Model):
    _name = "product.template"
    _inherit = ["product.template", "l10n_br_fiscal.product.mixin"]

    # mudando pra integer porque  a nota fiscal só aceita integer
    default_code = fields.Integer("Internal Reference", index=True)
    # no_barcode = fields.Boolean(
    #     "Não possui código de barras",
    #     compute="_compute_no_barcode",
    #     store=True,
    #     inverse="_set_no_barcode",
    # )

    no_barcode = fields.Boolean(
        "Não possui código de barras",
        inverse="_set_no_barcode",
        compute="_compute_no_barcode",
    )

    @api.depends("product_variant_ids.no_barcode")
    def _compute_no_barcode(self):
        self._compute_template_field_from_variant_field("no_barcode")

    def _set_no_barcode(self):
        self._set_product_variant_field("no_barcode")

    @api.constrains("no_barcode", "barcode")
    def _check_no_barcode(self):
        for record in self:
            print("barcode", record.no_barcode)
            print("barcode", record.barcode)
            if record.no_barcode and record.barcode:
                raise ValidationError(
                    _(
                        "O produto foi marcado como 'Não possui código de barras' "
                        "mas o código de barras foi informado: %s"
                    )
                    % record.barcode
                )

            if not record.no_barcode and not (record.barcode or "").strip():
                raise ValidationError(
                    _(
                        "O Código de Barras é obrigatório na nota fiscal se o produto tiver código de barras. Não informar o  Marque a opção 'Não possui código de barras' se o produto não tiver código de barras."
                    )
                )

    ncm_id = fields.Many2one(
        comodel_name="l10n_br_fiscal.ncm",
        string="NCM",
        compute="_compute_ncm_id",
        inverse="_set_ncm_id",
        required=True,
        store=True,
    )

    @api.depends("fiscal_type_id", "product_variant_ids.ncm_id")
    def _compute_ncm_id(self):
        # compute the ncm_id from the single product variant
        self._compute_template_field_from_variant_field("ncm_id")
        # if the fiscal type is service, set the ncm_id to the service ncm
        # despite the single product variant ncm_id
        for record in self:
            if record.fiscal_type_id.code == "09":  # service
                record.ncm_id = self.env.ref(NCM_FOR_SERVICE_REF)

    def _set_ncm_id(self):
        self._set_product_variant_field("ncm_id")

    cest_id = fields.Many2one(
        comodel_name="l10n_br_fiscal.cest",
        string="CEST",
        compute="_compute_cest_id",
        inverse="_set_cest_id",
        store=True,
    )

    @api.depends("product_variant_ids.cest_id")
    def _compute_cest_id(self):
        self._compute_template_field_from_variant_field("cest_id")

    def _set_cest_id(self):
        self._set_product_variant_field("cest_id")

    fiscal_type_id = fields.Many2one(
        comodel_name="l10n_br_fiscal.product.fiscal.type",
        string="Fiscal Type",
        required=True,
        compute="_compute_fiscal_type_id",
        inverse="_set_fiscal_type_id",
        store=True,
    )

    @api.depends("product_variant_ids.fiscal_type_id")
    def _compute_fiscal_type_id(self):
        self._compute_template_field_from_variant_field("fiscal_type_id")

    def _set_fiscal_type_id(self):
        self._set_product_variant_field("fiscal_type_id")

    icms_origin_id = fields.Many2one(
        comodel_name="l10n_br_fiscal.icms.origin",
        string="ICMS Origin",
        required=True,
        compute="_compute_icms_origin_id",
        inverse="_set_icms_origin_id",
        store=True,
    )

    @api.depends("product_variant_ids.icms_origin_id")
    def _compute_icms_origin_id(self):
        self._compute_template_field_from_variant_field("icms_origin_id")

    def _set_icms_origin_id(self):
        self._set_product_variant_field("icms_origin_id")

    # os dois primeiros digitos do ncm
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

    @api.depends("product_variant_ids.fiscal_additional_information")
    def _compute_fiscal_additional_information(self):
        self._compute_template_field_from_variant_field("fiscal_additional_information")

    def _set_fiscal_additional_information(self):
        self._set_product_variant_field("fiscal_additional_information")

    mrp_bom_id = fields.Many2one(
        comodel_name="mrp.bom",
        string="BoM",
        domain="[('product_tmpl_id', '=', id)]",
        inverse="_set_mrp_bom_id",
    )

    mrp_bom_line_ids = fields.One2many(
        related="mrp_bom_id.bom_line_ids",
        string="BoM Lines",
    )

    def _set_mrp_bom_id(self):
        self._set_product_variant_field("mrp_bom_id")

    @api.constrains("fiscal_type_id", "bom_ids")
    def _check_bom_required_for_fiscal_type(self):
        required_codes = ("03", "04")
        for product in self:
            company = product.company_id or self.env.company
            if company.country_id.code != "BR":
                continue
            fiscal_code = product.fiscal_type_id.code
            if fiscal_code in required_codes and not product.bom_ids:
                raise ValidationError(
                    _(
                        "O produto '%(product)s' possui tipo fiscal '%(fiscal_type)s'. "
                        "Produtos com tipo fiscal '03 - Produto em Processo' ou "
                        "'04 - Produto Acabado' devem possuir ao menos uma lista de materiais cadastrada.",
                        product=product.display_name,
                        fiscal_type=product.fiscal_type_id.display_name,
                    )
                )

    # Some modules of the repo depend on stock and have
    # demo products of type 'product' (this type is added to product.template
    # in the stock module).
    # For some reason when running the tests, some inverse method fields then fail when
    # reading 'product' value for the product type. It seems it is because
    # l10n_br_fiscal doesn't depend on stock. But we don't want such a dependency.
    # So a workaround to avoid the bug we add the 'product' value to the selection.
    # type = fields.Selection(
    #     selection_add=[("product", "Storable Product")],
    #     ondelete={"product": "set consu"},
    # )

    # @api.onchange("cest_id")
    # def _onchange_cest_id(self):
    #     print("onchange_cest_id")
    #     print(self.cest_id)
    #     print(self.ncm_id)
    #     if not self.cest_id:
    #         return
    #     if not self.ncm_id:
    #         self.cest_id = False
    #         return
    #     if self.cest_id and self.cest_id.ncms:
    #         ncm_codes = self.cest_id.ncms.split(",")
    #         print(ncm_codes)
    #         print(self.ncm_id.code_unmasked)
    #         if self.ncm_id.code_unmasked:
    #             # Check if ncm_id.code matches the beginning of any ncm_codes
    #             ncm_code_matches = any(
    #                 self.ncm_id.code_unmasked.strip().startswith(ncm_code.strip())
    #                 for ncm_code in ncm_codes
    #             )
    #             if not ncm_code_matches:
    #                 self.cest_id = False

    # @api.onchange('ncm_id')
    # def _get_cest_domain(self):
    #     print("ncm_id")
    #     print(self.ncm_id)
    #     print(type(self.ncm_id))
    #     if self.ncm_id:
    #         self.ncm_id.read(['code'])
    #         print('get_cest_domain')
    #         print(self.ncm_id.code)
    # ncm = self.env['l10n_br_fiscal.ncm'].browse(self.ncm_id)

    # print(ncm.code)
    # print(self.ncm_id)
    # print(self.ncm_id.code)
    # if not self.ncm_id:
    #     return [('id', '=', False)]  # Return empty domain

    # return [('ncm_ids.code', '=like', (self.ncm_id.code or "") + '%')]

    # You can customize this logic based on your needs
    # Option 1: Exact match with ncm_ids
    # return [('ncm_ids', 'in', self.ncm_id.id)]

    # Option 2: Partial match with ncms field using wildcards
    # This will match if the NCM code appears anywhere in the ncms string
    # return [('ncms', 'ilike', self.ncm_id.code)]

    # Option 2b: Using % wildcards with like operator
    # return [('ncm_ids.code', 'like', self.ncm_id.code + '%')]

    # Option 3: More complex wildcard matching
    # For example, if you want to match the first 4 digits: self.ncm_id.code[:4]
    # return [('ncms', 'ilike', self.ncm_id.code[:4])]

    # nbm_id = fields.Many2one(
    #     comodel_name="l10n_br_fiscal.nbm", index=True, string="NBM"
    # )

    # tax_icms_or_issqn = fields.Selection(
    #     selection=TAX_ICMS_OR_ISSQN,
    #     string="ICMS or ISSQN Tax",
    #     default=TAX_DOMAIN_ICMS,
    #     compute="_compute_tax_icms_or_issqn",
    #     store=True,
    #     readonly=False,
    # )

    # service_type_id = fields.Many2one(
    #     comodel_name="l10n_br_fiscal.service.type",
    #     string="Service Type LC 166",
    #     domain="[('internal_type', '=', 'normal')]",
    # )

    # city_taxation_code_id = fields.Many2many(
    #     comodel_name="l10n_br_fiscal.city.taxation.code", string="City Taxation Code"
    # )

    # fiscal_genre_code = fields.Char(
    #     related="fiscal_genre_id.code",
    #     store=True,
    #     string="Fiscal Product Genre Code",
    # )

    # ipi_guideline_class_id = fields.Many2one(
    #     comodel_name="l10n_br_fiscal.tax.ipi.guideline.class",
    #     string="IPI Guideline Class",
    # )

    # ipi_control_seal_id = fields.Many2one(
    #     comodel_name="l10n_br_fiscal.tax.ipi.control.seal", string="IPI Control Seal"
    # )

    # nbs_id = fields.Many2one(
    #     comodel_name="l10n_br_fiscal.nbs", index=True, string="NBS"
    # )

    # uoe_id = fields.Many2one(
    #     comodel_name="uom.uom",
    #     related="ncm_id.uoe_id",
    #     store=True,
    #     string="Export UoM",
    # )

    # uoe_factor = fields.Float(string="Export UoM Factor", default=1.00)

    # uot_id = fields.Many2one(comodel_name="uom.uom", string="Tax UoM")

    # uot_factor = fields.Float(string="Tax UoM Factor")
