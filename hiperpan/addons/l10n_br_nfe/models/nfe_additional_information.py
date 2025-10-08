from odoo import models, fields, api
from odoo.exceptions import ValidationError


class NFeAdditionalInformation(models.Model):
    _name = "l10n_br_nfe.nfe.additional_information"
    _description = "Informações Adicionais da NF-e"

    name = fields.Char(string="Nome", size=255)

    additional_information = fields.Text(string="Informações Adicionais", size=2000)
