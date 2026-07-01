from odoo import fields, models, api


class DfeNfeEscritItem(models.Model):
    _name = "l10n_br_dfe_monitor.dfe_nfe_escrit_item"
    _description = "Item da Escrituração de NF-e"

    dfe_nfe_escrit_id = fields.Many2one(
        "l10n_br_dfe_monitor.dfe_nfe_escrit",
        string="Escrituração de NF-e",
        ondelete="cascade",
    )

    proc_nfe_id = fields.Many2one(
        "l10n_br_dfe_monitor.proc_nfe",
        string="NF-e Processada",
        related="dfe_nfe_escrit_id.proc_nfe_id",
        readonly=True,
        store=True,
    )

    proc_nfe_item_id = fields.Many2one(
        "l10n_br_dfe_monitor.proc_nfe_item",
        string="Item da NF-e Processada",
        readonly=False,
        domain="[('proc_nfe_id', '=', proc_nfe_id)]",
        store=True,
    )

    likely_item_defaults_id = fields.Many2one(
        "l10n_br_dfe_monitor.dfe_nfe_escrit_item_defaults",
        string="Item de Escrituração de NF-e Padrão",
        ondelete="set null",
    )

    @api.onchange("proc_nfe_item_id")
    def _onchange_proc_nfe_item_id(self):
        for record in self:
            if record.proc_nfe_item_id:
                gtin = record.proc_nfe_item_id.c_ean
                cod_prod = record.proc_nfe_item_id.c_prod
                unit_text = record.proc_nfe_item_id.u_com
                cnpj = record.proc_nfe_id.emit_cnpj
                # cpf = record.proc_nfe_id.emit_cpf

                dfe_nfe_escrit_item_defaults_id = self.env[
                    "l10n_br_dfe_monitor.dfe_nfe_escrit_item_defaults"
                ].search(
                    [
                        ("gtin", "=", gtin),
                        ("cod_prod", "=", cod_prod),
                        ("unit_text", "=", unit_text),
                        ("cnpj", "=", cnpj),
                    ],
                    limit=1,
                )
                if dfe_nfe_escrit_item_defaults_id:
                    record.likely_item_defaults_id = dfe_nfe_escrit_item_defaults_id.id
                    record.product_id = dfe_nfe_escrit_item_defaults_id.product_id
                    record.uom_id = dfe_nfe_escrit_item_defaults_id.uom_id
                    record.own_use = dfe_nfe_escrit_item_defaults_id.own_use
                    record.cfop_id = dfe_nfe_escrit_item_defaults_id.cfop_id
                    record.icms_cst_id = dfe_nfe_escrit_item_defaults_id.icms_cst_id
                    record.ipi_cst_id = dfe_nfe_escrit_item_defaults_id.ipi_cst_id
                    record.pis_cst_id = dfe_nfe_escrit_item_defaults_id.pis_cst_id
                    record.cofins_cst_id = dfe_nfe_escrit_item_defaults_id.cofins_cst_id

    # Fields that are mirrored between an escrituração item and its defaults
    # record. Order is shared by create / compare / update so the three stay
    # in sync. Each entry is (item_field, defaults_field).
    _DEFAULT_TRACKED_FIELDS = [
        ("product_id", "product_id"),
        ("uom_id", "uom_id"),
        ("own_use", "own_use"),
        ("cfop_id", "cfop_id"),
        ("icms_cst_id", "icms_cst_id"),
        ("ipi_cst_id", "ipi_cst_id"),
        ("pis_cst_id", "pis_cst_id"),
        ("cofins_cst_id", "cofins_cst_id"),
    ]

    def _default_match_domain(self):
        """Search domain identifying the defaults record for this saved item."""
        self.ensure_one()
        return [
            ("gtin", "=", self.proc_nfe_item_id.c_ean),
            ("cod_prod", "=", self.proc_nfe_item_id.c_prod),
            ("unit_text", "=", self.proc_nfe_item_id.u_com),
            ("cnpj", "=", self.proc_nfe_id.emit_cnpj),
        ]

    def _default_values_from_item(self):
        """Defaults-record values dict built from this item's current values."""
        self.ensure_one()
        vals = {
            "gtin": self.proc_nfe_item_id.c_ean,
            "cod_prod": self.proc_nfe_item_id.c_prod,
            "unit_text": self.proc_nfe_item_id.u_com,
            "description": self.proc_nfe_item_id.x_prod,
            "cnpj": self.proc_nfe_id.emit_cnpj,
            "partner_id": self.dfe_nfe_escrit_id.partner_id.id,
        }
        for item_field, def_field in self._DEFAULT_TRACKED_FIELDS:
            value = self[item_field]
            if isinstance(value, models.BaseModel):
                value = value.id
            vals[def_field] = value
        return vals

    def _reconcile_default(self):
        """Reconcile one saved item against the item-defaults table.

        - No matching default yet -> create one silently, link it; no conflict.
        - A matching default exists but differs -> link it and flag a conflict
          (so the caller can offer the user a confirmation wizard).
        - Already matches -> link it; no conflict.

        :return: this item's recordset when its default differs (a conflict to
            confirm), or an empty recordset otherwise.
        """
        self.ensure_one()
        defaults_model = self.env["l10n_br_dfe_monitor.dfe_nfe_escrit_item_defaults"]
        # proc_nfe_item_id links to the processed NF-e line; reconciliation
        # needs it for GTIN, product code, unit, description, etc.
        if not self.proc_nfe_item_id:
            return self.browse()

        defaults = self.likely_item_defaults_id or defaults_model.search(
            self._default_match_domain(), limit=1
        )
        new_vals = self._default_values_from_item()

        if not defaults:
            defaults = defaults_model.create(new_vals)
            self.likely_item_defaults_id = defaults.id
            return self.browse()

        if self.likely_item_defaults_id != defaults:
            self.likely_item_defaults_id = defaults.id

        differs = any(
            self._defaults_field_differs(defaults, def_field, new_vals.get(def_field))
            for _item_field, def_field in self._DEFAULT_TRACKED_FIELDS
        )
        return self if differs else self.browse()

    def create_default_update_wizard(self):
        """Create the confirmation wizard for this item and return its id."""
        self.ensure_one()
        wizard_model = self.env["l10n_br_dfe_monitor.escrit_item_default_update_wizard"]
        return wizard_model.create_for_item(self).id

    @api.model
    def _defaults_field_differs(self, defaults, def_field, new_value):
        """Whether ``defaults[def_field]`` differs from the candidate ``new_value``."""
        current = defaults[def_field]
        if isinstance(current, models.BaseModel):
            return current.id != (new_value or False)
        return current != (new_value if new_value is not None else False)

    item_number = fields.Integer(
        string="Nº Item", related="proc_nfe_item_id.n_item", store=True
    )

    product_id = fields.Many2one(
        "product.product",
        string="Produto",
        ondelete="set null",
    )

    def domain_icms_cst_in_tax_id(self):
        return [
            ("tax_domain_id", "=", self.env.ref("l10n_br_fiscal.tax_domain_icms").id)
        ]

    icms_origin_id = fields.Many2one(
        "l10n_br_fiscal.icms.origin",
        string="Origem da Mercadoria",
        compute="_compute_icms_origin_id",
        store=True,
        readonly=True,
    )

    @api.depends("proc_nfe_item_id")
    def _compute_icms_origin_id(self):
        for record in self:
            if record.proc_nfe_item_id.icms_orig:
                record.icms_origin_id = self.env["l10n_br_fiscal.icms.origin"].search(
                    [("code", "=", record.proc_nfe_item_id.icms_orig)], limit=1
                )
            else:
                record.icms_origin_id = False

    icms_origin_code = fields.Char(
        string="Código ICMS Origin",
        related="icms_origin_id.code",
        store=True,
        readonly=True,
    )

    icms_cst_id = fields.Many2one(
        "l10n_br_fiscal.cst",
        string="ICMS CST",
        domain=domain_icms_cst_in_tax_id,
        compute="_compute_icms_cst_id",
        store=True,
        readonly=False,
        ondelete="set null",
    )

    @api.depends("own_use")
    def _compute_icms_cst_id(self):
        for record in self:
            if record.own_use:
                record.icms_cst_id = self.env.ref("l10n_br_fiscal.cst_icms_90")
            else:
                record.icms_cst_id = False

    cfop_id = fields.Many2one(
        "l10n_br_fiscal.cfop",
        string="CFOP",
        ondelete="set null",
        domain="[('type_in_out', '=', 'in')]",
    )

    stock_move = fields.Boolean(
        string="Movimentação de Estoque",
        default=True,
    )

    own_use = fields.Boolean(
        string="Own Use and Consumption",
        default=False,
    )

    quantity = fields.Float(
        string="Quantidade",
        digits=(11, 4),
        store=True,
        compute="_compute_quantity",
        readonly=False,
        required=True,
    )

    @api.depends("proc_nfe_item_id")
    def _compute_quantity(self):
        for record in self:
            if record.proc_nfe_item_id.q_com:
                record.quantity = record.proc_nfe_item_id.q_com
            else:
                record.quantity = False

    unit = fields.Char(
        string="Unidade",
        related="proc_nfe_item_id.u_com",
        store=True,
    )

    uom_id = fields.Many2one(
        "uom.uom",
        string="Unidade de Medida",
        compute="_compute_uom_id",
        store=True,
        readonly=False,
    )

    @api.depends("unit")
    def _compute_uom_id(self):
        for record in self:
            if record.unit:
                uom_id = self.env["uom.uom"].search(
                    [("nfe_name", "=", record.unit)], limit=1
                )
                if uom_id:
                    record.uom_id = uom_id
                else:
                    record.uom_id = self.env["uom.uom"].search(
                        [("dfe_uom_name_ids.name", "=", record.unit)], limit=1
                    )

    product_uom_id = fields.Many2one(
        "uom.uom",
        string="Unidade de Medida do Produto",
        related="product_id.uom_id",
        store=True,
    )

    stock_quantity = fields.Float(
        string="Quantidade entrante em estoque",
        digits=(11, 4),
        store=True,
        compute="_compute_stock_quantity",
        readonly=True,
    )

    @api.depends("uom_id", "quantity", "product_uom_id")
    def _compute_stock_quantity(self):
        for record in self:
            if record.uom_id and record.product_uom_id and record.quantity:
                record.stock_quantity = record.uom_id._compute_quantity(
                    record.quantity, record.product_uom_id
                )
            else:
                record.stock_quantity = False

    total_value = fields.Float(
        string="Valor Total Bruto",
        digits=(13, 2),
        related="proc_nfe_item_id.v_prod",
        store=True,
        readonly=True,
    )

    total_discount = fields.Float(
        string="Valor Total do Desconto",
        digits=(13, 2),
        related="proc_nfe_item_id.v_desc",
        store=True,
        readonly=True,
    )

    icms_tax_percent = fields.Float(
        string="Aliquota do ICMS",
        digits=(3, 4),
        compute="_compute_icms_tax_percent",
        store=True,
        readonly=True,
    )

    @api.depends("own_use", "proc_nfe_item_id.icms_p_icms")
    def _compute_icms_tax_percent(self):
        for record in self:
            if record.own_use:
                record.icms_tax_percent = False
            else:
                record.icms_tax_percent = record.proc_nfe_item_id.icms_p_icms

    icms_base = fields.Float(
        string="Base de Cálculo do ICMS",
        digits=(13, 2),
        compute="_compute_icms_base",
        store=True,
        readonly=True,
    )

    @api.depends("own_use", "proc_nfe_item_id.icms_v_bc")
    def _compute_icms_base(self):
        for record in self:
            if record.own_use:
                record.icms_base = False
            else:
                record.icms_base = record.proc_nfe_item_id.icms_v_bc

    icms_value = fields.Float(
        string="Valor do ICMS",
        digits=(13, 2),
        compute="_compute_icms_value",
        store=True,
        readonly=True,
    )

    @api.depends("own_use", "proc_nfe_item_id.icms_v_icms")
    def _compute_icms_value(self):
        for record in self:
            if record.own_use:
                record.icms_value = False
            else:
                record.icms_value = record.proc_nfe_item_id.icms_v_icms

    icms_st_tax_percent = fields.Float(
        string="Aliquota do ICMS ST",
        digits=(3, 4),
        related="proc_nfe_item_id.icms_p_icms_st",
        store=True,
        readonly=True,
    )

    icms_st_base = fields.Float(
        string="Base de Cálculo do ICMS ST",
        digits=(13, 2),
        related="proc_nfe_item_id.icms_v_bc_st",
        store=True,
        readonly=True,
    )

    icms_st_value = fields.Float(
        string="Valor do ICMS ST",
        digits=(13, 2),
        related="proc_nfe_item_id.icms_v_icms_st",
        store=True,
        readonly=True,
    )

    def domain_ipi_cst_in_tax_id(self):
        return [
            ("tax_domain_id", "=", self.env.ref("l10n_br_fiscal.tax_domain_ipi").id)
        ]

    ipi_cst_id = fields.Many2one(
        "l10n_br_fiscal.cst",
        string="IPI CST",
        domain=domain_ipi_cst_in_tax_id,
        ondelete="set null",
        compute="_compute_ipi_cst_id",
        store=True,
        readonly=False,
    )

    @api.depends("own_use", "proc_nfe_item_id.ipi_cst")
    def _compute_ipi_cst_id(self):
        for record in self:
            if record.own_use:
                record.ipi_cst_id = False

    ipi_tax_percent = fields.Float(
        string="Aliquota do IPI",
        digits=(3, 4),
        compute="_compute_ipi_tax_percent",
        store=True,
        readonly=True,
    )

    @api.depends("own_use", "proc_nfe_item_id.ipi_p_ipi")
    def _compute_ipi_tax_percent(self):
        for record in self:
            if record.own_use:
                record.ipi_tax_percent = False
            else:
                record.ipi_tax_percent = record.proc_nfe_item_id.ipi_p_ipi

    ipi_base = fields.Float(
        string="Base de Cálculo do IPI",
        digits=(13, 2),
        compute="_compute_ipi_base",
        store=True,
        readonly=True,
    )

    @api.depends("own_use", "proc_nfe_item_id.ipi_v_bc")
    def _compute_ipi_base(self):
        for record in self:
            if record.own_use:
                record.ipi_base = False
            else:
                record.ipi_base = record.proc_nfe_item_id.ipi_v_bc

    ipi_value = fields.Float(
        string="Valor do IPI",
        digits=(13, 2),
        compute="_compute_ipi_value",
        store=True,
        readonly=True,
    )

    @api.depends("own_use", "proc_nfe_item_id.ipi_v_ipi")
    def _compute_ipi_value(self):
        for record in self:
            if record.own_use:
                record.ipi_value = False
            else:
                record.ipi_value = record.proc_nfe_item_id.ipi_v_ipi

    is_regime_real = fields.Boolean(
        string="É Regime Real",
        compute="_compute_is_regime_real",
    )

    @api.depends(
        "proc_nfe_item_id.proc_nfe_id.company_id.fiscal_framework",
        "proc_nfe_item_id.proc_nfe_id.company_id.regular_framework_type",
    )
    def _compute_is_regime_real(self):
        for record in self:
            if (
                record.proc_nfe_item_id.proc_nfe_id.company_id.fiscal_framework == "3"
                and record.proc_nfe_item_id.proc_nfe_id.company_id.regular_framework_type
                == "LR"
            ):
                record.is_regime_real = True
            else:
                record.is_regime_real = False

    allow_pis_cofins = fields.Boolean(
        string="Permite PIS e COFINS",
        compute="_compute_allow_pis_cofins",
        store=True,
        readonly=True,
    )

    @api.depends("is_regime_real", "own_use")
    def _compute_allow_pis_cofins(self):
        for record in self:
            if record.is_regime_real and not record.own_use:
                record.allow_pis_cofins = True
            else:
                record.allow_pis_cofins = False

    def domain_pis_cst_in_tax_id(self):
        return [
            (
                "tax_domain_id",
                "=",
                self.env.ref("l10n_br_fiscal.tax_domain_piscofins").id,
            )
        ]

    pis_cst_id = fields.Many2one(
        "l10n_br_fiscal.cst",
        string="PIS CST",
        domain=domain_pis_cst_in_tax_id,
        ondelete="set null",
        compute="_compute_pis_cst_id",
        store=True,
        readonly=False,
    )

    @api.depends("allow_pis_cofins", "proc_nfe_item_id.pis_cst")
    def _compute_pis_cst_id(self):
        for record in self:
            if not record.allow_pis_cofins:
                record.pis_cst_id = False

    pis_tax_percent = fields.Float(
        string="Aliquota do PIS",
        digits=(3, 4),
        compute="_compute_pis_tax_percent",
        store=True,
        readonly=True,
    )

    @api.depends("allow_pis_cofins", "proc_nfe_item_id.pis_p_pis")
    def _compute_pis_tax_percent(self):
        for record in self:
            if not record.allow_pis_cofins:
                record.pis_tax_percent = False
            else:
                record.pis_tax_percent = record.proc_nfe_item_id.pis_p_pis

    pis_tax_unit = fields.Float(
        string="Aliquota em reais (Tributado por unidade)",
        digits=(11, 4),
        compute="_compute_pis_tax_unit",
        store=True,
        readonly=True,
    )

    @api.depends("allow_pis_cofins", "proc_nfe_item_id.pis_v_aliq_prod")
    def _compute_pis_tax_unit(self):
        for record in self:
            if not record.allow_pis_cofins:
                record.pis_tax_unit = False
            else:
                record.pis_tax_unit = record.proc_nfe_item_id.pis_v_aliq_prod

    pis_bc_value = fields.Float(
        string="Valor da Base de Calculo do PIS",
        digits=(13, 2),
        compute="_compute_pis_bc_value",
        store=True,
        readonly=True,
    )

    @api.depends("allow_pis_cofins", "proc_nfe_item_id.pis_v_bc")
    def _compute_pis_bc_value(self):
        for record in self:
            if not record.allow_pis_cofins:
                record.pis_bc_value = False
            else:
                record.pis_bc_value = record.proc_nfe_item_id.pis_v_bc

    pis_bc_quantity = fields.Float(
        string="Quantidade (Tributado por quantidade)",
        digits=(12, 4),
        compute="_compute_pis_bc_quantity",
        store=True,
        readonly=True,
    )

    @api.depends("allow_pis_cofins", "proc_nfe_item_id.pis_q_bc_prod")
    def _compute_pis_bc_quantity(self):
        for record in self:
            if not record.allow_pis_cofins:
                record.pis_bc_quantity = False
            else:
                record.pis_bc_quantity = record.proc_nfe_item_id.pis_q_bc_prod

    pis_value = fields.Float(
        string="Valor do PIS",
        digits=(13, 2),
        compute="_compute_pis_value",
        store=True,
        readonly=True,
    )

    @api.depends("allow_pis_cofins", "proc_nfe_item_id.pis_v_pis")
    def _compute_pis_value(self):
        for record in self:
            if not record.allow_pis_cofins:
                record.pis_value = False
            else:
                record.pis_value = record.proc_nfe_item_id.pis_v_pis

    def domain_cofins_cst_in_tax_id(self):
        return [
            (
                "tax_domain_id",
                "=",
                self.env.ref("l10n_br_fiscal.tax_domain_piscofins").id,
            )
        ]

    cofins_cst_id = fields.Many2one(
        "l10n_br_fiscal.cst",
        string="COFINS CST",
        domain=domain_cofins_cst_in_tax_id,
        ondelete="set null",
        compute="_compute_cofins_cst_id",
        store=True,
        readonly=False,
    )

    @api.depends("allow_pis_cofins", "proc_nfe_item_id.cofins_cst")
    def _compute_cofins_cst_id(self):
        for record in self:
            if not record.allow_pis_cofins:
                record.cofins_cst_id = False

    cofins_tax_percent = fields.Float(
        string="Aliquota do COFINS",
        digits=(3, 4),
        compute="_compute_cofins_tax_percent",
        store=True,
        readonly=True,
    )

    @api.depends("allow_pis_cofins", "proc_nfe_item_id.cofins_p_cofins")
    def _compute_cofins_tax_percent(self):
        for record in self:
            if not record.allow_pis_cofins:
                record.cofins_tax_percent = False
            else:
                record.cofins_tax_percent = record.proc_nfe_item_id.cofins_p_cofins

    cofins_tax_unit = fields.Float(
        string="Aliquota em reais (Tributado por unidade)",
        digits=(11, 4),
        compute="_compute_cofins_tax_unit",
        store=True,
        readonly=True,
    )

    @api.depends("allow_pis_cofins", "proc_nfe_item_id.cofins_v_aliq_prod")
    def _compute_cofins_tax_unit(self):
        for record in self:
            if not record.allow_pis_cofins:
                record.cofins_tax_unit = False
            else:
                record.cofins_tax_unit = record.proc_nfe_item_id.cofins_v_aliq_prod

    cofins_bc_value = fields.Float(
        string="Valor da Base de Calculo do COFINS",
        digits=(13, 2),
        compute="_compute_cofins_bc_value",
        store=True,
        readonly=True,
    )

    @api.depends("allow_pis_cofins", "proc_nfe_item_id.cofins_v_bc")
    def _compute_cofins_bc_value(self):
        for record in self:
            if not record.allow_pis_cofins:
                record.cofins_bc_value = False
            else:
                record.cofins_bc_value = record.proc_nfe_item_id.cofins_v_bc

    cofins_bc_quantity = fields.Float(
        string="Quantidade (Tributado por quantidade)",
        digits=(12, 4),
        compute="_compute_cofins_bc_quantity",
        store=True,
        readonly=True,
    )

    @api.depends("allow_pis_cofins", "proc_nfe_item_id.cofins_q_bc_prod")
    def _compute_cofins_bc_quantity(self):
        for record in self:
            if not record.allow_pis_cofins:
                record.cofins_bc_quantity = False
            else:
                record.cofins_bc_quantity = record.proc_nfe_item_id.cofins_q_bc_prod

    cofins_value = fields.Float(
        string="Valor do COFINS",
        digits=(13, 2),
        compute="_compute_cofins_value",
        store=True,
        readonly=True,
    )

    @api.depends("allow_pis_cofins", "proc_nfe_item_id.cofins_v_cofins")
    def _compute_cofins_value(self):
        for record in self:
            if not record.allow_pis_cofins:
                record.cofins_value = False
            else:
                record.cofins_value = record.proc_nfe_item_id.cofins_v_cofins
