from odoo import models, fields, api


class Partner(models.Model):
    _name = "res.partner"
    _inherit = ["res.partner", "l10n_br_fiscal.party.mixin"]
