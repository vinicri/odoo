from odoo import models, fields

from .constants import NFE_OPERATION_TYPE


class NfeOperationNature(models.Model):
    _name = "l10n_br_nfe.nfe.operation_nature"
    _description = "Natureza da Operação"

    name = fields.Char(string="Name", size=60, required=True)

    type = fields.Selection(
        NFE_OPERATION_TYPE, string="Tipo de Operação", required=True
    )

    # nfe_documents = fields.One2many(
    #     comodel_name="l10n_br_nfe.nfe.document",
    #     inverse_name="operation_nature_id",
    #     string="Documentos NF-e",
    # )
