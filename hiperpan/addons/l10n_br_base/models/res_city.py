from odoo import models, fields

class City(models.Model):
    _inherit = 'res.city'

    ibge_code = fields.Char(string="IBGE Code", size=7, index=True)
