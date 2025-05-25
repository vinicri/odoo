from odoo import models, fields

class Partner(models.Model):
    _name = 'res.partner'
    _inherit = ['res.partner', 'l10n_br_base.party.mixin']

    l10n_br_base_is_accountant = fields.Boolean(string="Is accountant?", help="Mark this partner as an accountant so it can be added as an accountant of a company.")
    l10n_br_base_is_accountant_crc_code = fields.Char(string="CRC Code", help="CRC Code of the accountant.")
    