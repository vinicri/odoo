from odoo import models, fields

class CountryState(models.Model):
    _inherit = 'res.country.state'

    l10n_br_base_ibge_code = fields.Char(string="IBGE Code", size=2)