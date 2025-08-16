from odoo import models, fields


class UoM(models.Model):
    _inherit = "uom.uom"

    nfe_name = fields.Char(
        string="Nome na NFE/NFCE", size=6, help="Name of the UOM for NFE"
    )
