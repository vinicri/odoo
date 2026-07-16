from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class UoM(models.Model):
    _inherit = "uom.uom"

    available_for_dfe_in = fields.Boolean(
        string="Permitir uso na entrada de documentos fiscais", default=False
    )

    dfe_uom_name_ids = fields.One2many(
        "l10n_br_dfe_monitor.dfe_uom_name",
        "uom_id",
        string="Nome da Unidade de Medida na NF-e Emitida",
    )
