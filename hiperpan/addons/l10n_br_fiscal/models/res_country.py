from odoo import models, fields


class ResCountry(models.Model):
    _inherit = "res.country"

    bacen_code = fields.Integer(string="BACEN Code")
