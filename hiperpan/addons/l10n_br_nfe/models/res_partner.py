from odoo import models, fields


class ResPartner(models.Model):
    _name = "res.partner"
    _inherit = "res.partner"

    nfe_document_email = fields.Char(string="Email para recepção da NF-e", size=60)
