from odoo import fields, models


class StockPicking(models.Model):
    _inherit = "stock.picking"

    dfe_nfe_escrit_id = fields.Many2one(
        "l10n_br_dfe_monitor.dfe_nfe_escrit",
        string="Escrituração de NF-e",
        readonly=True,
        index=True,
        help=(
            "Escrituração de NF-e que originou esta transferência "
            "(recebimento ou devolução)."
        ),
    )
