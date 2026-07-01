from odoo import api, fields, models


class DfeNfeEscrit(models.Model):
    _name = "l10n_br_dfe_monitor.dfe_nfe_escrit"
    _description = "Escrituração de NF-e"

    proc_nfe_id = fields.Many2one(
        "l10n_br_dfe_monitor.proc_nfe",
        string="NF-e Processada",
        ondelete="set null",
        readonly=True,
        index=True,
    )

    item_ids = fields.One2many(
        comodel_name="l10n_br_dfe_monitor.dfe_nfe_escrit_item",
        inverse_name="dfe_nfe_escrit_id",
        string="Itens",
        ondelete="cascade",
    )

    def reconcile_item_defaults(self):
        """Reconcile every item of this escrituração against the defaults table.

        Called by the form view right after a save. Missing defaults are created
        silently; the ids of items whose existing default differs are returned so
        the client can open one confirmation wizard per conflicting item.

        :return: list of conflicting ``dfe_nfe_escrit_item`` ids (may be empty).
        """
        conflicts = self.env["l10n_br_dfe_monitor.dfe_nfe_escrit_item"]
        for item in self.item_ids:
            conflicts |= item._reconcile_default()
        return conflicts.ids

    # save this in case the proc_nfe_id is deleted
    nfe_key = fields.Char(
        string="Chave de Acesso",
        related="proc_nfe_id.ch_nfe",
        store=True,
        index=True,
    )

    nfe_number = fields.Char(
        string="Número da NF-e",
        related="proc_nfe_id.n_nf",
        store=True,
    )

    nfe_series = fields.Char(
        string="Série da NF-e",
        related="proc_nfe_id.serie",
        store=True,
    )

    issue_datetime = fields.Datetime(
        string="Data de Emissão",
        related="proc_nfe_id.dh_emi",
        store=True,
    )

    departure_datetime = fields.Datetime(
        string="Data de Saída",
        related="proc_nfe_id.dh_sai_ent",
        store=True,
    )

    arrival_datetime = fields.Datetime(
        string="Data de Chegada",
        required=True,
    )

    payment_type = fields.Selection(
        [("0", "À vista"), ("1", "À prazo"), ("2", "Outros")],
        string="Tipo de Pagamento",
        compute="_compute_payment_type",
        store=True,
    )

    @api.depends("proc_nfe_id.pag_ids.ind_pag")
    def _compute_payment_type(self):
        for rec in self:
            if rec.proc_nfe_id.pag_ids.ind_pag == "0":
                rec.payment_type = "0"
            elif rec.proc_nfe_id.pag_ids.ind_pag == "1":
                rec.payment_type = "1"
            else:
                rec.payment_type = "2"

    freight_type = fields.Selection(
        [
            ("0", "CIF (por conta do Remetente)"),
            ("1", "FOB (por conta do Destinatário)"),
            ("2", "Por conta de Terceiros"),
            ("3", "Transporte Próprio por conta do Remetente"),
            ("4", "Transporte Próprio por conta do Destinatário"),
            ("9", "Sem Ocorrência de Transporte"),
        ],
        string="Modalidade do Frete",
        compute="_compute_freight_type",
        store=True,
    )

    @api.depends("proc_nfe_id.transp_mod_frete")
    def _compute_freight_type(self):
        for rec in self:
            rec.freight_type = rec.proc_nfe_id.transp_mod_frete

    total_icms_base = fields.Float(
        string="Base de Cálculo do ICMS",
        digits=(13, 2),
        related="proc_nfe_id.v_bc",
        store=True,
    )

    total_icms_value = fields.Float(
        string="Valor do ICMS",
        digits=(13, 2),
        related="proc_nfe_id.v_icms",
        store=True,
    )

    total_icms_st_base = fields.Float(
        string="Base de Cálculo do ICMS ST",
        digits=(13, 2),
        related="proc_nfe_id.v_bc_st",
        store=True,
    )

    total_icms_st_value = fields.Float(
        string="Valor do ICMS ST",
        digits=(13, 2),
        related="proc_nfe_id.v_st",
        store=True,
    )

    total_nfe = fields.Float(
        string="Valor Total da NF-e",
        digits=(13, 2),
        related="proc_nfe_id.v_nf",
        store=True,
    )

    total_products = fields.Float(
        string="Valor das Mercadorias",
        digits=(13, 2),
        related="proc_nfe_id.v_prod",
        store=True,
    )

    total_discount = fields.Float(
        string="Valor do Desconto",
        digits=(13, 2),
        related="proc_nfe_id.v_desc",
        store=True,
    )

    total_freight = fields.Float(
        string="Valor do Frete",
        digits=(13, 2),
        related="proc_nfe_id.v_frete",
        store=True,
    )

    total_insurance = fields.Float(
        string="Valor do Seguro",
        digits=(13, 2),
        related="proc_nfe_id.v_seg",
        store=True,
    )

    total_other_expenses = fields.Float(
        string="Outras Despesas",
        digits=(13, 2),
        related="proc_nfe_id.v_outro",
        store=True,
    )

    total_ipi = fields.Float(
        string="Valor do IPI",
        digits=(13, 2),
        related="proc_nfe_id.v_ipi",
        store=True,
    )

    total_pis = fields.Float(
        string="Valor do PIS",
        digits=(13, 2),
        related="proc_nfe_id.v_pis",
        store=True,
    )

    total_cofins = fields.Float(
        string="Valor da COFINS",
        digits=(13, 2),
        related="proc_nfe_id.v_cofins",
        store=True,
    )

    partner_id = fields.Many2one(
        "res.partner",
        string="Parceiro",
        required=True,
        ondelete="cascade",
        compute="_compute_partner_id",
        store=True,
        readonly=False,
        index=True,
    )

    @api.depends("proc_nfe_id.emit_cnpj", "proc_nfe_id.emit_cpf")
    def _compute_partner_id(self):
        for rec in self:
            vat = rec.proc_nfe_id.emit_cnpj or rec.proc_nfe_id.emit_cpf
            if vat:
                partner = self.env["res.partner"].search([("vat", "=", vat)], limit=1)
                rec.partner_id = partner
            else:
                rec.partner_id = False

    _sql_constraints = [
        (
            "proc_nfe_id_unique",
            "UNIQUE(proc_nfe_id)",
            "Cada NF-e processada só pode ter uma escrituração.",
        )
    ]
