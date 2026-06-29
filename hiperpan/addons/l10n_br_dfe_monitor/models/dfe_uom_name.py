from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class DfeUomName(models.Model):
    _name = "l10n_br_dfe_monitor.dfe_uom_name"
    _description = "Nome da Unidade de Medida na NF-e Emitida"

    name = fields.Char(string="Nome", required=True, size=6)

    uom_id = fields.Many2one(
        "uom.uom",
        string="Unidade de Medida",
        required=True,
        ondelete="cascade",
    )

    _sql_constraints = [
        (
            "name_uniq",
            "unique(name)",
            "O Nome da Unidade de Medida na NF-e Emitida deve ser único.",
        ),
    ]
