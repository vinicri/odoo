from odoo import models, fields, api

class NFeTechContact(models.Model):
    _name = 'l10n_br_nfe.nfe.tech.contact'
    _description = 'Contato do Responsável Técnico'


    name = fields.Char(string='Nome', size=60, required=True)
    email = fields.Char(string='Email', size=60, required=True)
    phone = fields.Char(string='Telefone', size=14, required=True)
    csrt_identifier = fields.Char(string='CSRT', size=2, required=True)
    csrt_hash = fields.Char(string='Hash CSRT', size=28, required=True)