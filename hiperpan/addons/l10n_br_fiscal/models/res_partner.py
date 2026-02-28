from odoo import _, models, fields, api
from odoo.exceptions import ValidationError


class Partner(models.Model):
    _name = "res.partner"
    _inherit = ["res.partner", "l10n_br_fiscal.party.mixin"]

    is_freight_carrier = fields.Boolean(string="É transportadora", default=False)

    freight_carrier_vehicle_ids = fields.One2many(
        comodel_name="l10n_br_fiscal.freight.carrier.vehicle",
        string="Veículos de transporte",
        inverse_name="partner_id",
    )
