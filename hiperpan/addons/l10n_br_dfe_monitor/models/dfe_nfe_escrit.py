from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
from odoo.tools.float_utils import float_compare
from odoo.tools.misc import formatLang


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

    picking_id = fields.Many2one(
        "stock.picking",
        string="Recebimento de Estoque",
        readonly=True,
        copy=False,
        help=(
            "Transferência de recebimento criada a partir dos itens desta "
            "escrituração marcados como 'Movimentação de Estoque'."
        ),
    )

    @api.constrains("item_ids")
    def _check_items_confirmed(self):
        for record in self:
            unconfirmed = record.item_ids.filtered(lambda item: not item.confirmed)
            if unconfirmed:
                raise ValidationError(
                    _(
                        "Todos os itens da escrituração devem estar marcados "
                        "como conferidos antes de salvar. Itens não "
                        "conferidos: %(items)s."
                    )
                    % {
                        "items": ", ".join(
                            str(item.item_number) for item in unconfirmed
                        )
                    }
                )

    @api.constrains("item_ids")
    def _check_items_quantity_matches_nfe(self):
        """The sum of item_ids.quantity for a given proc_nfe_item_id must
        match that line's own quantity (proc_nfe_item.q_com) -- an item can
        be split across several escrituração lines (e.g. different CFOP/CST
        for part of the received quantity), but the totals must reconcile.
        """
        for record in self:
            totals_by_proc_item = {}
            for item in record.item_ids:
                proc_item = item.proc_nfe_item_id
                if not proc_item:
                    continue
                totals_by_proc_item[proc_item] = (
                    totals_by_proc_item.get(proc_item, 0.0) + item.quantity
                )

            mismatches = [
                (proc_item, total)
                for proc_item, total in totals_by_proc_item.items()
                # precision_digits=4 because the q_com field has 4 decimal places
                if float_compare(total, proc_item.q_com, precision_digits=4) != 0
            ]
            if mismatches:
                raise ValidationError(
                    _(
                        "A soma das quantidades dos itens da escrituração não "
                        "confere com a quantidade da NF-e para os seguintes "
                        "itens:\n%(details)s"
                    )
                    % {
                        "details": "\n".join(
                            _(
                                "- Item %(n_item)s (%(name)s): total escriturado %(total)s | total NF-e %(expected)s"
                            )
                            % {
                                "n_item": proc_item.n_item,
                                "name": proc_item.x_prod,
                                "total": formatLang(self.env, total, digits=4),
                                "expected": formatLang(
                                    self.env, proc_item.q_com, digits=4
                                ),
                            }
                            for proc_item, total in mismatches
                        )
                    }
                )

    @api.model
    def default_get(self, fields_list):
        defaults = super().default_get(fields_list)
        proc_nfe_id = defaults.get("proc_nfe_id") or self.env.context.get(
            "default_proc_nfe_id"
        )
        proc_nfe = (
            self.env["l10n_br_dfe_monitor.proc_nfe"].browse(proc_nfe_id)
            if proc_nfe_id
            else self.env["l10n_br_dfe_monitor.proc_nfe"]
        )
        if (
            "arrival_datetime" in fields_list
            and proc_nfe
            and not defaults.get("arrival_datetime")
        ):
            anchor = proc_nfe.dh_sai_ent
            if anchor:
                company = proc_nfe.company_id or self.env.company
                suggested = company._get_next_receiving_datetime(anchor)
            if suggested:
                defaults["arrival_datetime"] = suggested
        if "item_ids" in fields_list and proc_nfe and not defaults.get("item_ids"):
            item_model = self.env["l10n_br_dfe_monitor.dfe_nfe_escrit_item"]
            commands = []
            for proc_item in proc_nfe.item_ids:
                # dfe_nfe_escrit_id itself can't be set (the parent record is
                # still unsaved), so proc_nfe_id must be set directly here --
                # it's needed for proc_nfe_item_id's domain
                # ([('proc_nfe_id', '=', proc_nfe_id)]) to resolve to this
                # NF-e's own items instead of matching nothing. See the
                # comment on dfe_nfe_escrit_item.proc_nfe_id for why it's a
                # plain field (not related) and must be in the item list view.
                vals = {
                    "proc_nfe_item_id": proc_item.id,
                    "proc_nfe_id": proc_nfe.id,
                }
                vals.update(item_model._get_prefill_vals_from_proc_item(proc_item))
                commands.append((0, 0, vals))
            if commands:
                defaults["item_ids"] = commands
        return defaults

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

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records.proc_nfe_id.write({"estado_escrituracao": "escriturado"})
        records._sync_stock_picking()
        return records

    # item_ids fields that affect the resulting stock movement; any other
    # change (CFOP, ICMS CST, confirmed, ...) doesn't need to touch the
    # picking at all.
    _STOCK_RELEVANT_ITEM_FIELDS = {
        "product_id",
        "quantity",
        "uom_id",
        "product_uom_id",
        "stock_move",
        "proc_nfe_item_id",
    }

    def _item_ids_vals_affect_stock(self, item_commands):
        """Whether an item_ids command list (as found in a write()'s vals)
        could change the resulting stock movement: a line added/removed, or
        an existing line's product/quantity/uom/stock_move changed."""
        for command in item_commands:
            code = command[0]
            if code in (0, 1):  # create / update
                line_vals = command[2] or {}
                if code == 0 or self._STOCK_RELEVANT_ITEM_FIELDS.intersection(
                    line_vals
                ):
                    return True
            elif code in (2, 3, 4, 5, 6):  # delete/unlink/link/clear/set
                return True
        return False

    def write(self, vals):
        res = super().write(vals)
        if "item_ids" in vals and self._item_ids_vals_affect_stock(vals["item_ids"]):
            self._sync_stock_picking()
        return res

    def unlink(self):
        proc_nfe = self.proc_nfe_id
        pickings_to_return = self.picking_id.filtered(lambda p: p.state == "done")
        res = super().unlink()
        proc_nfe.write({"estado_escrituracao": "pendente"})
        for picking in pickings_to_return:
            self._return_picking(picking)
        return res

    def _get_stock_move_vals_list(self, picking):
        """One stock.move per confirmed item flagged for stock movement.

        Items without a product (shouldn't happen once _check_items_confirmed
        passes, but stay defensive) or explicitly excluded via stock_move are
        skipped.
        """
        self.ensure_one()
        vals_list = []
        for item in self.item_ids:
            if not item.stock_move or not item.product_id or not item.stock_quantity:
                continue
            vals_list.append(
                {
                    "name": item.product_id.display_name,
                    "picking_id": picking.id,
                    "product_id": item.product_id.id,
                    "product_uom_qty": item.stock_quantity,
                    "product_uom": item.product_id.uom_id.id,
                    "location_id": picking.location_id.id,
                    "location_dest_id": picking.location_dest_id.id,
                    "company_id": picking.company_id.id,
                    "picking_type_id": picking.picking_type_id.id,
                }
            )
        return vals_list

    def _create_and_validate_picking(self):
        """Create, confirm and validate a receipt for this escrituração's
        current stock-moving items. Returns the picking, or an empty
        recordset if there's nothing to move."""
        self.ensure_one()
        # check all items have a product id and are flagged for stock movement
        if not self.item_ids.filtered(lambda item: item.stock_move and item.product_id):
            return self.env["stock.picking"]

        company = self.proc_nfe_id.company_id or self.env.company
        warehouse = self.env["stock.warehouse"].search(
            [("company_id", "=", company.id)], limit=1
        )
        if not warehouse or not warehouse.in_type_id:
            raise UserError(
                _(
                    "Configure um armazém com tipo de operação de "
                    "Recebimento para a empresa %(company)s antes de "
                    "escriturar itens com movimentação de estoque."
                )
                % {"company": company.display_name}
            )

        picking = self.env["stock.picking"].create(
            {
                "picking_type_id": warehouse.in_type_id.id,
                "partner_id": self.partner_id.id,
                "origin": self.nfe_key or self.proc_nfe_id.display_name,
                "company_id": company.id,
                "scheduled_date": self.arrival_datetime or fields.Datetime.now(),
            }
        )
        move_vals_list = self._get_stock_move_vals_list(picking)
        if not move_vals_list:
            picking.unlink()
            return self.env["stock.picking"]

        self.env["stock.move"].create(move_vals_list)
        picking.action_confirm()
        picking.action_assign()
        for move in picking.move_ids:
            move.quantity = move.product_uom_qty
        picking.with_context(skip_backorder=True).button_validate()
        return picking

    def _return_picking(self, picking):
        """Fully return a done receipt (reverses its quants), mirroring
        stock.return.picking's own _create_return/_prepare_move_default_values
        but driven directly, since that wizard is built for interactive use.
        """
        return_picking = picking.copy(
            {
                "move_ids": [],
                "picking_type_id": (
                    picking.picking_type_id.return_picking_type_id.id
                    or picking.picking_type_id.id
                ),
                "state": "draft",
                "origin": _("Devolução de %s", picking.name),
                "location_id": picking.location_dest_id.id,
                "location_dest_id": picking.location_id.id,
            }
        )
        for move in picking.move_ids.filtered(lambda m: m.state == "done"):
            move.copy(
                {
                    "picking_id": return_picking.id,
                    "product_uom_qty": move.quantity,
                    "location_id": return_picking.location_id.id,
                    "location_dest_id": return_picking.location_dest_id.id,
                    "state": "draft",
                    "origin_returned_move_id": move.id,
                    "procure_method": "make_to_stock",
                }
            )
        return_picking.action_confirm()
        return_picking.action_assign()
        for move in return_picking.move_ids:
            move.quantity = move.product_uom_qty
        return_picking.with_context(skip_backorder=True).button_validate()
        return return_picking

    def _sync_stock_picking(self):
        """Keep each escrituração's stock receipt in sync with its current
        item lines.

        - No picking yet: create and validate one from the current items.
        - Picking still not done (shouldn't normally happen, since it's
          validated immediately): just recreate it from scratch.
        - Picking already done: it can't be edited/cancelled directly (Odoo
          only allows reversing a done move via a return), so return it in
          full and create a fresh, corrected one.
        """
        for record in self:
            old_picking = record.picking_id
            if old_picking:
                if old_picking.state == "done":
                    record._return_picking(old_picking)
                else:
                    old_picking.action_cancel()
                    old_picking.unlink()
                record.picking_id = False

            new_picking = record._create_and_validate_picking()
            record.picking_id = new_picking.id if new_picking else False
