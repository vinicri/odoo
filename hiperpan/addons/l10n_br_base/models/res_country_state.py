from odoo import models, fields

class CountryState(models.Model):
    _inherit = 'res.country.state'

    ibge_code = fields.Char(string="IBGE Code", size=2)