"""
Wizard calculadora de preço de venda, aberto a partir do campo Preço de Venda
no "Criar Produto".

Mostra o item da NF-e processada (nome, unidade e quantidade comercial) para o
usuário se situar sobre a que quantidade o custo se refere, e permite ajustar
a margem de lucro ou o preço final, cada um recalculando o outro.
"""

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class DfePriceCalculatorWizard(models.TransientModel):
    _name = "l10n_br_dfe_monitor.price_calculator_wizard"
    _description = "Calculadora de Preço de Venda"

    proc_nfe_item_id = fields.Many2one(
        "l10n_br_dfe_monitor.proc_nfe_item",
        string="Item da NF-e Processada",
        readonly=True,
    )

    # Read-only context fields, shown so the user can reason about what
    # quantity the NF-e line's unit cost refers to.
    proc_nfe_item_name = fields.Char(
        string="Descrição na NF-e", related="proc_nfe_item_id.x_prod", readonly=True
    )
    proc_nfe_item_unit = fields.Char(
        string="Unidade na NF-e", related="proc_nfe_item_id.u_com", readonly=True
    )
    proc_nfe_item_quantity = fields.Float(
        string="Quantidade na NF-e",
        related="proc_nfe_item_id.q_com",
        readonly=True,
    )

    # Unit cost from the NF-e line (e.g. price paid per box).
    line_unit_cost = fields.Float(
        string="Custo por Unidade da NF-e",
        related="proc_nfe_item_id.v_un_com",
        readonly=True,
    )

    # How many sales units (the product's own uom_id) fit in one NF-e line
    # unit -- e.g. the box costs line_unit_cost and holds this many units.
    quantity_per_line_unit = fields.Float(
        string="Quantidade de Vendas por Unidade da NF-e",
        digits=(11, 4),
        default=1.0,
    )

    cost_per_unit = fields.Float(
        string="Custo por Unidade de Venda",
        digits="Product Price",
        compute="_compute_cost_per_unit",
        store=True,
    )

    @api.depends("line_unit_cost", "quantity_per_line_unit")
    def _compute_cost_per_unit(self):
        for record in self:
            if record.quantity_per_line_unit:
                record.cost_per_unit = (
                    record.line_unit_cost / record.quantity_per_line_unit
                )
            else:
                record.cost_per_unit = 0.0

    margin = fields.Float(
        string="Margem (%)",
        digits=(6, 2),
        default=lambda self: self.env.company.dfe_default_product_margin,
    )

    unit_price = fields.Float(
        string="Preço de Venda",
        digits="Product Price",
    )

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        # Seed unit_price from cost_per_unit/margin so the dialog opens with
        # a sensible value already filled in, instead of 0.0 until the user
        # touches margin or unit_price themselves (which is when
        # _onchange_margin/_onchange_unit_price take over).
        for record in records:
            if record.cost_per_unit and not record.unit_price:
                record.unit_price = record.cost_per_unit * (1 + record.margin / 100)
        return records

    @api.onchange("cost_per_unit", "margin")
    def _onchange_margin(self):
        """Recompute unit_price from cost_per_unit/margin, unless the user
        just edited unit_price directly (see _onchange_unit_price)."""
        for record in self:
            if record.cost_per_unit:
                record.unit_price = record.cost_per_unit * (1 + record.margin / 100)

    @api.onchange("unit_price")
    def _onchange_unit_price(self):
        """Recompute margin from the user-edited unit_price, keeping
        cost_per_unit fixed."""
        for record in self:
            if record.cost_per_unit:
                record.margin = (
                    record.unit_price / record.cost_per_unit - 1
                ) * 100

    @api.constrains("quantity_per_line_unit")
    def _check_quantity_per_line_unit(self):
        for record in self:
            if record.quantity_per_line_unit <= 0:
                raise ValidationError(
                    _("A quantidade de vendas por unidade da NF-e deve ser maior que 0.")
                )
