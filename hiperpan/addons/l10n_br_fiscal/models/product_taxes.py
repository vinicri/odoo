from odoo import _, api, models, fields
from odoo.exceptions import ValidationError

ICMS_BC_MODALITY = [
    ("0", "Margem Valor Agregado (%)"),
    ("1", "Pauta (valor)"),
    ("2", "Preço Tabelado Máximo (valor)"),
    ("3", "Valor da Operação"),
]


class ProductTaxes(models.Model):
    _name = "l10n_br_fiscal.product.taxes"
    _description = "Product Taxes"

    company_id = fields.Many2one(
        "res.company",
        "Company",
        required=True,
        default=lambda self: self.env.company,
        store=True,
        readonly=True,
    )

    product_id = fields.Many2one(
        "product.product",
        "Variação do Produto Principal",
        check_company=True,
        index=True,
    )

    product_tmpl_id = fields.Many2one(
        "product.template",
        "Produto Principal",
        check_company=True,
        index=True,
    )

    @api.constrains("product_id", "product_tmpl_id")
    def _check_product_id_and_product_tmpl_id(self):
        for record in self:
            if not record.product_id and not record.product_tmpl_id:
                raise ValidationError(
                    _(
                        "O produto principal ou a variação do produto principal deve ser informado."
                    )
                )
            if record.product_id and record.product_tmpl_id:
                raise ValidationError(
                    _(
                        "Apenas uma das opções deve ser informada: produto principal ou variação do produto principal."
                    )
                )

    def icms_sn_tax_id_domain(self):
        return [
            ("tax_group_id", "=", self.env.ref("l10n_br_fiscal.tax_group_icmssn").id)
        ]

    icms_sn_tax_id = fields.Many2one(
        comodel_name="l10n_br_fiscal.tax",
        string="ICMS SN",
        domain=icms_sn_tax_id_domain,
    )

    icms_sn_cst_code = fields.Char(
        related="icms_sn_tax_id.cst_out_code",
        string="Código CST ICMS SN",
        readonly=True,
    )

    icms_sn_cst_nfe_code = fields.Char(
        compute="_compute_icms_sn_cst_nfe_code",
        string="Código CST ICMS SN",
        readonly=True,
    )

    icms_origin_code = fields.Char(
        string="Código ICMS Origin",
        compute="_compute_icms_origin_code",
        readonly=True,
    )

    @api.depends("product_id.icms_origin_id", "product_tmpl_id.icms_origin_id")
    def _compute_icms_origin_code(self):
        for record in self:
            if record.product_id:
                record.icms_origin_code = record.product_id.icms_origin_id.code
            else:
                record.icms_origin_code = record.product_tmpl_id.icms_origin_id.code

    @api.depends("icms_sn_tax_id.cst_out_code", "icms_origin_code")
    def _compute_icms_sn_cst_nfe_code(self):
        for record in self:
            if record.icms_origin_code and record.icms_sn_tax_id.cst_out_code:
                record.icms_sn_cst_nfe_code = (
                    f"{record.icms_origin_code}{record.icms_sn_tax_id.cst_out_code}"
                )
            else:
                record.icms_sn_cst_nfe_code = False

    def domain_icms_tax_id(self):
        return [("tax_group_id", "=", self.env.ref("l10n_br_fiscal.tax_group_icms").id)]

    icms_tax_id = fields.Many2one(
        comodel_name="l10n_br_fiscal.tax",
        string="ICMS",
        domain=domain_icms_tax_id,
    )

    icms_cst_code = fields.Char(
        related="icms_tax_id.cst_out_code",
        string="Código CST ICMS",
        readonly=True,
    )

    icms_cst_nfe_code = fields.Char(
        compute="_compute_icms_cst_nfe_code",
        string="Código CST ICMS",
        readonly=True,
    )

    @api.depends("icms_tax_id.cst_out_code", "icms_origin_code")
    def _compute_icms_cst_nfe_code(self):
        for record in self:
            if record.icms_origin_code and record.icms_tax_id.cst_out_code:
                record.icms_cst_nfe_code = (
                    f"{record.icms_origin_code}{record.icms_tax_id.cst_out_code}"
                )
            else:
                record.icms_cst_nfe_code = False

    has_icms_own_operation = fields.Boolean(
        string="Tributado em operação própria",
        compute="_compute_has_icms_own_operation",
        store=True,
    )

    @api.depends("icms_cst_code")
    def _compute_has_icms_own_operation(self):
        for record in self:
            record.has_icms_own_operation = record.icms_cst_code in (
                "00",
                "10",
                "20",
                "51",
                "70",
            )

    is_deferment_cst = fields.Boolean(
        string="É CST de deferimento",
        compute="_compute_is_deferment_cst",
        store=True,
    )

    @api.depends("icms_cst_code")
    def _compute_is_deferment_cst(self):
        for record in self:
            record.is_deferment_cst = record.icms_cst_code == "51"

    is_icms_with_base_reduction = fields.Boolean(
        string="É CST com redução de base de calculo",
        compute="_compute_is_icms_with_base_reduction",
        store=True,
    )

    @api.depends("icms_cst_code")
    def _compute_is_icms_with_base_reduction(self):
        for record in self:
            record.is_icms_with_base_reduction = record.icms_cst_code in ("20", "70")

    icms_bc_modality = fields.Selection(
        string="Modalidade da Base de Calculo",
        selection=ICMS_BC_MODALITY,
        compute="_compute_icms_bc_modality",
        readonly=False,
        store=True,
    )

    @api.depends("has_icms_own_operation")
    def _compute_icms_bc_modality(self):
        for record in self:
            if record.has_icms_own_operation:
                record.icms_bc_modality = "0"
            else:
                record.icms_bc_modality = False

    @api.constrains("has_icms_own_operation", "is_deferment_cst", "icms_bc_modality")
    def _check_icms_bc_modality(self):
        for record in self:
            if (
                record.has_icms_own_operation
                and not record.is_deferment_cst
                and not record.icms_bc_modality
            ):
                raise ValidationError(
                    _(
                        "A modalidade da base de calculo do ICMS é obrigatória para o ICMS escolhido."
                    )
                )

    icms_bc_reduction_percent = fields.Float(
        string="Percentual de Redução da Base de Calculo",
        digits=(3, 4),
        compute="_compute_icms_bc_reduction_percent",
        store=True,
        readonly=False,
    )

    @api.depends("is_icms_with_base_reduction")
    def _compute_icms_bc_reduction_percent(self):
        for record in self:
            if not record.is_icms_with_base_reduction:
                record.icms_bc_reduction_percent = False

    @api.constrains("is_icms_with_base_reduction")
    def _check_icms_bc_reduction_percent(self):
        for record in self:
            if (
                record.is_icms_with_base_reduction
                and not record.icms_bc_reduction_percent
            ):
                raise ValidationError(
                    _(
                        "O percentual de redução da base de calculo do ICMS é obrigatório para o ICMS escolhido."
                    )
                )
            if (
                record.icms_bc_reduction_percent
                and not record.is_icms_with_base_reduction
            ):
                raise ValidationError(
                    _(
                        "O percentual de redução da base de calculo do ICMS não pode ser informado para o ICMS escolhido."
                    )
                )

    icms_tax_percent = fields.Float(
        related="icms_tax_id.percent_amount",
        string="Aliquota",
        digits=(3, 4),
        readonly=True,
        store=True,
    )

    icms_deferment_percent = fields.Float(
        string="Percentual de Deferimento",
        digits=(3, 4),
        compute="_compute_icms_deferment_percent",
        store=True,
        readonly=False,
    )

    @api.depends("is_deferment_cst")
    def _compute_icms_deferment_percent(self):
        for record in self:
            if not record.is_deferment_cst:
                record.icms_deferment_percent = False

    @api.constrains("is_deferment_cst")
    def _check_icms_deferment_percent(self):
        for record in self:
            if record.is_deferment_cst and not record.icms_deferment_percent:
                raise ValidationError(
                    _(
                        "O percentual de deferimento do ICMS é obrigatório para o ICMS escolhido."
                    )
                )
            elif record.icms_deferment_percent and not record.is_deferment_cst:
                raise ValidationError(
                    _(
                        "O percentual de deferimento do ICMS não pode ser informado para o ICMS escolhido."
                    )
                )

    def _domain_icms_fcp_tax_id(self):
        return [
            ("tax_group_id", "=", self.env.ref("l10n_br_fiscal.tax_group_icmsfcp").id)
        ]

    icms_fcp_tax_id = fields.Many2one(
        comodel_name="l10n_br_fiscal.tax",
        string="FCP",
        domain=_domain_icms_fcp_tax_id,
        compute="_compute_icms_fcp_tax_id",
        store=True,
        readonly=False,
    )

    @api.depends("has_icms_own_operation")
    def _compute_icms_fcp_tax_id(self):
        for record in self:
            if not record.has_icms_own_operation:
                record.icms_fcp_tax_id = False

    icms_fcp_tax_percent = fields.Float(
        related="icms_fcp_tax_id.percent_amount",
        string="Aliquota do FCP",
        digits=(3, 4),
        store=True,
        readonly=True,
    )

    is_icms_st = fields.Boolean(
        string="É CST com ICMS ST",
        compute="_compute_is_icms_st",
        store=True,
    )

    @api.depends("icms_cst_code", "icms_sn_cst_code")
    def _compute_is_icms_st(self):
        for record in self:
            record.is_icms_st = record.icms_cst_code in (
                "10",
                "30",
                "70",
            ) or record.icms_sn_cst_code in (
                "201",
                "202",
                "203",
            )

    icms_st_modality = fields.Selection(
        string="Modalidade da Base de Calculo do ICMS ST",
        selection=[
            ("0", "Preço tabelado ou máximo sugerido"),
            ("1", "Lista Negativa (valor)"),
            ("2", "Lista Positiva (valor)"),
            ("3", "Lista Neutra (valor)"),
            ("4", "Margem Valor Agregado (%)"),
            ("5", "Pauta (valor)"),
            ("6", "Valor da operação"),
        ],
        compute="_compute_icms_st_modality",
        readonly=False,
        store=True,
    )

    @api.depends("is_icms_st")
    def _compute_icms_st_modality(self):
        for record in self:
            if not record.is_icms_st:
                record.icms_st_modality = False
            else:
                record.icms_st_modality = "4"

    is_icms_st_mva_modality = fields.Boolean(
        string="É modalidade de base de calculo do ICMS ST MVA",
        compute="_compute_is_icms_st_mva_modality",
        store=True,
    )

    @api.depends("icms_st_modality")
    def _compute_is_icms_st_mva_modality(self):
        for record in self:
            record.is_icms_st_mva_modality = record.icms_st_modality == "4"

    icms_st_mva_percent = fields.Float(
        string="MVA ICMS ST",
        digits=(3, 4),
        compute="_compute_icms_st_mva_percent",
        store=True,
        readonly=False,
    )

    @api.depends("is_icms_st_mva_modality")
    def _compute_icms_st_mva_percent(self):
        for record in self:
            if not record.is_icms_st_mva_modality:
                record.icms_st_mva_percent = False

    icms_st_reduction_percent = fields.Float(
        string="Percentual de Redução da Base de Calculo do ICMS ST",
        digits=(3, 4),
        compute="_compute_icms_st_reduction_percent",
        store=True,
        readonly=False,
    )

    @api.depends("is_icms_st")
    def _compute_icms_st_reduction_percent(self):
        for record in self:
            if not record.is_icms_st:
                record.icms_st_reduction_percent = False

    icms_st_tax_percent = fields.Float(
        related="icms_tax_id.percent_amount",
        string="Aliquota do ICMS ST",
        digits=(3, 4),
        readonly=True,
    )

    def _domain_icms_st_fcp_tax_id(self):
        return [
            (
                "tax_group_id",
                "=",
                self.env.ref("l10n_br_fiscal.tax_group_icmsfcp_st").id,
            )
        ]

    icms_st_fcp_tax_id = fields.Many2one(
        comodel_name="l10n_br_fiscal.tax",
        string="FCP ST",
        domain=_domain_icms_st_fcp_tax_id,
        compute="_compute_icms_st_fcp_tax_id",
        store=True,
        readonly=False,
    )

    @api.depends("is_icms_st")
    def _compute_icms_st_fcp_tax_id(self):
        for record in self:
            if not record.is_icms_st:
                record.icms_st_fcp_tax_id = False

    icms_st_fcp_tax_percent = fields.Float(
        related="icms_st_fcp_tax_id.percent_amount",
        string="Aliquota do FCP ST",
        digits=(3, 4),
        store=True,
        readonly=True,
    )
