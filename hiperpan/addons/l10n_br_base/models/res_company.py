from odoo import models, fields

class Company(models.Model):
    _name = 'res.company'
    _inherit = ['res.company', 'l10n_br_base.party.mixin']

    # l10n_br_base_cnpj_code = fields.Char(string="CNPJ", help="National Registry of Legal Entities.")

    l10n_br_base_accountant_id = fields.Many2one(
        comodel_name="res.partner", 
        string="Accountant", 
        help="Accountant of the company.",
        domain="[('l10n_br_base_is_accountant', '=', True)]"
    )




    #validação de cnpj
    #validação de ie


