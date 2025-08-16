from odoo import models, fields

OPERATION_TYPE = [("0", "Entrada"), ("1", "Saída")]


class NfeOperationNature(models.Model):
    _name = "l10n_br_nfe.nfe.operation_nature"
    _description = "Natureza da Operação"

    name = fields.Char(string="Name", size=60, required=True)

    type = fields.Selection(OPERATION_TYPE, string="Tipo de Operação", required=True)
