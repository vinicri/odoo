"""
Extensão de res.company para DFe Monitor
"""
from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    dfe_last_nsu = fields.Char(
        string="Último NSU DFe",
        help="Último NSU recebido na consulta NFeDistribuicaoDFe. Atualizado automaticamente.",
    )
    dfe_max_nsu = fields.Char(
        string="Maior NSU disponível",
        help="Maior NSU disponível no Ambiente Nacional para esta empresa.",
    )
