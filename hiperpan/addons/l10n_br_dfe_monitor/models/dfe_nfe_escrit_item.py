from odoo import fields, models, api, _
from odoo.exceptions import ValidationError


class DfeNfeEscritItem(models.Model):
    _name = "l10n_br_dfe_monitor.dfe_nfe_escrit_item"
    _description = "Item da Escrituração de NF-e"

    dfe_nfe_escrit_id = fields.Many2one(
        "l10n_br_dfe_monitor.dfe_nfe_escrit",
        string="Escrituração de NF-e",
        ondelete="cascade",
    )

    # Plain stored field, not related="dfe_nfe_escrit_id.proc_nfe_id": for
    # unsaved rows (dfe_nfe_escrit_id not set yet, e.g. bulk-created from a
    # NF-e in dfe_nfe_escrit.default_get), a related field would recompute
    # to False the moment the client re-derives it, silently overwriting
    # whatever value was set explicitly. Must also be declared in the item
    # list view (see views/dfe_nfe_escrit_item.xml) or it never reaches the
    # row's data at all -- see the comment there for why.
    proc_nfe_id = fields.Many2one(
        "l10n_br_dfe_monitor.proc_nfe",
        string="NF-e Processada",
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

    @api.model
    def _get_prefill_vals_from_proc_item(self, proc_item):
        """Build the defaults-derived vals for one proc_nfe_item.

        Shared by the single-item onchange (UI) and the bulk item creation
        when opening the escrituração from a NF-e (default_get on
        dfe_nfe_escrit), so both paths apply the exact same lookup/matching
        logic against dfe_nfe_escrit_item_defaults.

        :return: a vals dict (may be empty if there's no matching default).
        """
        gtin = proc_item.c_ean
        cod_prod = proc_item.c_prod
        unit_text = proc_item.u_com
        cnpj = proc_item.proc_nfe_id.emit_cnpj

        defaults = self.env["l10n_br_dfe_monitor.dfe_nfe_escrit_item_defaults"].search(
            [
                ("gtin", "=", gtin),
                ("cod_prod", "=", cod_prod),
                ("unit_text", "=", unit_text),
                ("cnpj", "=", cnpj),
            ],
            limit=1,
        )

        cfop_to = self._resolve_cfop_id_to(
            proc_item.cfop,
            defaults.product_id.fiscal_type_id.id if defaults.product_id else False,
        )

        icms_cst_to = self._resolve_icms_cst_id_to(proc_item.icms_cst_csosn)

        if not defaults:
            # No saved defaults: still suggest CFOP via from-to (no fiscal
            # type yet; remapped again when product_id is set in the UI).
            return {
                **({"cfop_id": cfop_to.id} if cfop_to else {}),
                **({"icms_cst_id": icms_cst_to.id} if icms_cst_to else {}),
            }

        product_uom_id = defaults.product_id.uom_id
        default_uom_id = defaults.uom_id
        is_default_uom_id_valid = (
            default_uom_id.category_id == product_uom_id.category_id
        )

        return {
            "likely_item_defaults_id": defaults.id,
            "product_id": defaults.product_id.id,
            "uom_id": default_uom_id.id if is_default_uom_id_valid else False,
            "own_use": defaults.own_use,
            "cfop_id": defaults.cfop_id.id,
            "icms_cst_id": defaults.icms_cst_id.id,
            "ipi_cst_id": defaults.ipi_cst_id.id,
            "pis_cst_id": defaults.pis_cst_id.id,
            "cofins_cst_id": defaults.cofins_cst_id.id,
        }

    @api.onchange("proc_nfe_item_id")
    def _onchange_proc_nfe_item_id(self):
        for record in self:
            if record.proc_nfe_item_id:
                vals = record._get_prefill_vals_from_proc_item(record.proc_nfe_item_id)
                if vals:
                    record.update(vals)

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

    @api.onchange(*[item_field for item_field, _def_field in _DEFAULT_TRACKED_FIELDS])
    def _onchange_tracked_fields_reset_confirmed(self):
        # Any manual edit to prefilled data means it needs re-confirming.
        for record in self:
            record.confirmed = False

    @api.model
    def reconcile_default_from_values(self, item_values):
        """Reconcile an (unsaved) item's values against the item-defaults table.

        Called from the item modal's Save before the line is committed, so
        ``item_values`` holds the line's current in-memory values rather than a
        stored record. It must contain ``proc_nfe_item_id`` and may contain
        ``dfe_nfe_escrit_id`` plus the tracked item fields.

        - No matching default yet -> create one silently.
        - A matching default exists but differs -> create a confirmation wizard.
        - Already matches -> nothing.

        :return: ``{"wizard_id": id, "diff_html": html}`` when the default
            differs (for the client to render a confirmation dialog), otherwise
            ``False``.
        """
        proc_item = self.env["l10n_br_dfe_monitor.proc_nfe_item"].browse(
            item_values.get("proc_nfe_item_id")
        )
        # proc_nfe_item_id is the link to the processed NF-e line (proc_nfe_item).
        # Reconciliation needs that line for GTIN, product code, unit, description, etc.
        if not proc_item:
            return False

        emit_cnpj = proc_item.proc_nfe_id.emit_cnpj

        defaults_model = self.env["l10n_br_dfe_monitor.dfe_nfe_escrit_item_defaults"]
        likely_id = item_values.get("likely_item_defaults_id")
        defaults = (
            defaults_model.browse(likely_id)
            if likely_id
            else defaults_model.search(
                [
                    ("gtin", "=", proc_item.c_ean),
                    ("cod_prod", "=", proc_item.c_prod),
                    ("unit_text", "=", proc_item.u_com),
                    ("cnpj", "=", emit_cnpj),
                ],
                limit=1,
            )
        )

        partner_id = self.env["res.partner"].search([("vat", "=", emit_cnpj)], limit=1)
        new_vals = {
            "gtin": proc_item.c_ean,
            "cod_prod": proc_item.c_prod,
            "unit_text": proc_item.u_com,
            "description": proc_item.x_prod,
            "cnpj": emit_cnpj,
            "partner_id": partner_id.id,
        }
        for item_field, def_field in self._DEFAULT_TRACKED_FIELDS:
            new_vals[def_field] = item_values.get(item_field) or False

        if not defaults:
            defaults_model.create(new_vals)
            return False

        differs = any(
            self._defaults_field_differs(defaults, def_field, new_vals.get(def_field))
            for _item_field, def_field in self._DEFAULT_TRACKED_FIELDS
        )
        if not differs:
            return False

        wizard = self.env[
            "l10n_br_dfe_monitor.escrit_item_default_update_wizard"
        ].create_for_defaults(defaults, new_vals)
        return {"wizard_id": wizard.id, "diff_html": wizard.diff_html}

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

    confirmed = fields.Boolean(
        string="Conferido",
        help="Marque para confirmar que os dados pré-preenchidos deste item foram conferidos.",
    )

    is_missing_required = fields.Boolean(
        string="Faltam Campos Obrigatórios",
        compute="_compute_is_missing_required",
        store=True,
    )

    @api.depends("product_id", "uom_id", "cfop_id", "icms_cst_id", "quantity")
    def _compute_is_missing_required(self):
        for record in self:
            record.is_missing_required = not (
                record.product_id
                and record.uom_id
                and record.cfop_id
                and record.icms_cst_id
                and record.quantity
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

    icms_cst_code_from = fields.Char(
        string="Código ICMS CST From",
        related="proc_nfe_item_id.icms_cst_csosn",
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
        required=True,
    )

    @api.model
    def _resolve_icms_cst_id_to(self, icms_cst_code_from):
        if not icms_cst_code_from:
            return self.env["l10n_br_fiscal.cst"]
        tax_domain_ids = [
            self.env.ref("l10n_br_fiscal.tax_domain_icms").id,
            self.env.ref("l10n_br_fiscal.tax_domain_icmssn").id,
        ]
        cst_from_to = self.env["l10n_br_dfe_monitor.cst_escrit_from_to"].search(
            [
                ("cst_id_from.code_unmasked", "=", icms_cst_code_from),
                ("cst_id_from.tax_domain_id", "in", tax_domain_ids),
            ],
            limit=1,
        )
        return cst_from_to.cst_id_to if cst_from_to else self.env["l10n_br_fiscal.cst"]

    @api.depends("own_use", "icms_cst_code_from")
    def _compute_icms_cst_id(self):
        for record in self:
            if record.own_use:
                record.icms_cst_id = self.env.ref("l10n_br_fiscal.cst_icms_90")
            elif record.icms_cst_code_from:
                record.icms_cst_id = self._resolve_icms_cst_id_to(
                    record.icms_cst_code_from
                )
            else:
                record.icms_cst_id = False

    icms_cst_code = fields.Char(
        string="Código ICMS CST",
        related="icms_cst_id.code",
        store=True,
        readonly=True,
    )

    cfop_code_from = fields.Char(
        string="CFOP From",
        related="proc_nfe_item_id.cfop",
        store=True,
        readonly=True,
    )

    cfop_id = fields.Many2one(
        "l10n_br_fiscal.cfop",
        string="CFOP",
        domain="[('type_in_out', '=', 'in')]",
        required=True,
    )

    @api.model
    def _resolve_cfop_id_to(self, cfop_code_from, fiscal_type_id=False):
        """Map an incoming CFOP code (+ optional fiscal type) to a CFOP to use.

        Prefers an exact fiscal-type rule, then falls back to rules with no
        fiscal type (match any product). Returns an empty recordset if none.
        """
        if not cfop_code_from:
            return self.env["l10n_br_fiscal.cfop"]
        CfopFromTo = self.env["l10n_br_dfe_monitor.cfop_escrit_from_to"]
        domain_cfop = [("cfop_id_from.code", "=", cfop_code_from)]
        cfop_from_to = CfopFromTo.search(
            domain_cfop + [("fiscal_type_id", "=", fiscal_type_id or False)],
            limit=1,
        )
        if not cfop_from_to and fiscal_type_id:
            cfop_from_to = CfopFromTo.search(
                domain_cfop + [("fiscal_type_id", "=", False)],
                limit=1,
            )
        return (
            cfop_from_to.cfop_id_to if cfop_from_to else self.env["l10n_br_fiscal.cfop"]
        )

    @api.onchange("product_id", "cfop_code_from", "own_use")
    def _onchange_product_id_cfop_from_to(self):
        # Trigger on product_id (not fiscal_type_id / cfop_code_from): onchange
        # only accepts direct field names the UI edits. Related fields never
        # appear as "changed" themselves, and dotted paths are ignored.
        for record in self:
            if not record.cfop_code_from:
                continue
            fiscal_type_id = (
                self.env.ref("l10n_br_fiscal.product_fiscal_type_07").id
                if record.own_use
                else record.product_id.fiscal_type_id.id if record.product_id else False
            )

            record.cfop_id = record._resolve_cfop_id_to(
                record.cfop_code_from, fiscal_type_id
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

    likely_uom_multiplier = fields.Float(
        string="Fator de Conversão da Unidade de Medida",
        compute="_compute_likely_uom_multiplier",
        store=True,
        readonly=True,
    )

    @api.depends("product_uom_category_id")
    def _compute_likely_uom_multiplier(self):
        for record in self:
            record.likely_uom_multiplier = 12.0

    likely_uom_rounding = fields.Float(
        string="Precisão de Arredondamento da Unidade de Medida",
        compute="_compute_likely_uom_rounding",
        readonly=True,
    )

    @api.depends("product_uom_category_id")
    def _compute_likely_uom_rounding(self):
        categ_unit = self.env.ref("uom.product_uom_categ_unit")
        categ_kgm = self.env.ref("uom.product_uom_categ_kgm")
        categ_vol = self.env.ref("uom.product_uom_categ_vol")
        for record in self:
            category = record.product_uom_category_id
            if category == categ_unit:
                record.likely_uom_rounding = 1.0
            elif category == categ_kgm:
                record.likely_uom_rounding = 0.001
            elif category == categ_vol:
                record.likely_uom_rounding = 0.001
            else:
                record.likely_uom_rounding = 1.0

    uom_id = fields.Many2one(
        "uom.uom",
        string="Unidade de Medida",
        compute="_compute_uom_id",
        domain="[('category_id', '=', product_uom_category_id)]",
        store=True,
        readonly=False,
        required=True,
    )

    @api.depends("product_id")
    def _compute_uom_id(self):
        for record in self:
            if not record.product_id:
                record.uom_id = False

    product_uom_id = fields.Many2one(
        "uom.uom",
        string="Unidade de Medida do Produto",
        related="product_id.uom_id",
        store=True,
    )

    product_uom_category_id = fields.Many2one(
        related="product_id.uom_id.category_id",
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

    should_include_icms = fields.Boolean(
        string="Deve incluir ICMS",
        compute="_compute_should_include_icms",
    )

    @api.depends("own_use", "icms_cst_code")
    def _compute_should_include_icms(self):
        for record in self:
            if record.own_use or record.icms_cst_code in ["30", "40", "41", "50", "60"]:
                record.should_include_icms = False
            else:
                record.should_include_icms = True

    icms_tax_percent = fields.Float(
        string="Aliquota do ICMS",
        digits=(3, 4),
        compute="_compute_icms_tax_percent",
        store=True,
        readonly=True,
    )

    @api.depends("should_include_icms", "proc_nfe_item_id.icms_p_icms")
    def _compute_icms_tax_percent(self):
        for record in self:
            if record.should_include_icms:
                record.icms_tax_percent = record.proc_nfe_item_id.icms_p_icms
            else:
                record.icms_tax_percent = False

    icms_base = fields.Float(
        string="Base de Cálculo do ICMS",
        digits=(13, 2),
        compute="_compute_icms_base",
        store=True,
        readonly=True,
    )

    @api.depends("should_include_icms", "proc_nfe_item_id.icms_v_bc")
    def _compute_icms_base(self):
        for record in self:
            if record.should_include_icms:
                record.icms_base = record.proc_nfe_item_id.icms_v_bc
            else:
                record.icms_base = False

    icms_value = fields.Float(
        string="Valor do ICMS",
        digits=(13, 2),
        compute="_compute_icms_value",
        store=True,
        readonly=True,
    )

    @api.depends("should_include_icms", "proc_nfe_item_id.icms_v_icms")
    def _compute_icms_value(self):
        for record in self:
            if record.should_include_icms:
                record.icms_value = record.proc_nfe_item_id.icms_v_icms
            else:
                record.icms_value = False

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

    should_include_ipi = fields.Boolean(
        string="Deve incluir IPI",
        compute="_compute_should_include_ipi",
    )

    @api.depends("own_use", "product_id.fiscal_type_id")
    def _compute_should_include_ipi(self):
        for record in self:
            if not record.own_use and record.product_id.fiscal_type_id in [
                self.env.ref("l10n_br_fiscal.product_fiscal_type_01"),
                self.env.ref("l10n_br_fiscal.product_fiscal_type_06"),
            ]:
                record.should_include_ipi = True
            else:
                record.should_include_ipi = False

    def domain_ipi_cst_in_tax_id(self):
        return [
            ("tax_domain_id", "=", self.env.ref("l10n_br_fiscal.tax_domain_ipi").id),
            ("cst_type", "=", "in"),
        ]

    @api.model
    def _resolve_ipi_cst_id_to(self, ipi_cst_code_from):
        if not ipi_cst_code_from:
            return self.env["l10n_br_fiscal.cst"]
        cst_from_to = self.env["l10n_br_dfe_monitor.cst_escrit_from_to"].search(
            [
                ("cst_id_from.code_unmasked", "=", ipi_cst_code_from),
                (
                    "cst_id_from.tax_domain_id",
                    "=",
                    self.env.ref("l10n_br_fiscal.tax_domain_ipi").id,
                ),
            ],
            limit=1,
        )
        return cst_from_to.cst_id_to if cst_from_to else self.env["l10n_br_fiscal.cst"]

    @api.onchange("should_include_ipi", "ipi_cst_code_from")
    def _onchange_should_include_ipi(self):
        for record in self:
            if record.should_include_ipi:
                record.ipi_cst_id = self._resolve_ipi_cst_id_to(record.ipi_cst_code_from)
            else:
                record.ipi_cst_id = False

    ipi_cst_code_from = fields.Char(
        string="IPI CST Code From",
        related="proc_nfe_item_id.ipi_cst",
        store=True,
        readonly=True,
    )

    ipi_cst_id = fields.Many2one(
        "l10n_br_fiscal.cst",
        string="IPI CST",
        domain=domain_ipi_cst_in_tax_id,
        ondelete="set null",
        compute="_compute_ipi_cst_id",
        store=True,
        readonly=False,
    )

    @api.constrains("ipi_cst_id")
    def _check_ipi_cst_id(self):
        for record in self:
            if record.should_include_ipi and not record.ipi_cst_id:
                raise ValidationError(
                    _(
                        "O IPI CST é obrigatório para o produto %(product)s, que gera crédito de IPI, como matéria-prima e produto intermediário."
                    )
                    % {
                        "product": record.proc_nfe_item_id.x_prod
                        or record.product_id.display_name,
                    }
                )

    @api.depends("should_include_ipi")
    def _compute_ipi_cst_id(self):
        for record in self:
            if not record.should_include_ipi:
                record.ipi_cst_id = False

    ipi_tax_percent = fields.Float(
        string="Aliquota do IPI",
        digits=(3, 4),
        compute="_compute_ipi_tax_percent",
        store=True,
        readonly=True,
    )

    @api.depends("should_include_ipi")
    def _compute_ipi_tax_percent(self):
        for record in self:
            if record.should_include_ipi:
                record.ipi_tax_percent = record.proc_nfe_item_id.ipi_p_ipi
            else:
                record.ipi_tax_percent = False

    ipi_base = fields.Float(
        string="Base de Cálculo do IPI",
        digits=(13, 2),
        compute="_compute_ipi_base",
        store=True,
        readonly=True,
    )

    @api.depends("should_include_ipi")
    def _compute_ipi_base(self):
        for record in self:
            if record.should_include_ipi:
                record.ipi_base = record.proc_nfe_item_id.ipi_v_bc
            else:
                record.ipi_base = False

    ipi_value = fields.Float(
        string="Valor do IPI",
        digits=(13, 2),
        compute="_compute_ipi_value",
        store=True,
        readonly=True,
    )

    @api.depends("should_include_ipi")
    def _compute_ipi_value(self):
        for record in self:
            if record.should_include_ipi:
                record.ipi_value = record.proc_nfe_item_id.ipi_v_ipi
            else:
                record.ipi_value = False

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
