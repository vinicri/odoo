from odoo import models, fields, api
from odoo.exceptions import ValidationError
from odoo.tools import single_email_re
from ..models.utils import format_br_phone
from erpbrasil.base.fiscal import cnpj_cpf


class NFeTechContact(models.Model):
    _name = "l10n_br_nfe.nfe.tech.contact"
    _description = "Contato do Responsável Técnico"

    name = fields.Char(string="Nome", size=60, required=True)

    cnpj = fields.Char(
        string="CNPJ", size=14, compute="_compute_cnpj", store=True, readonly=True
    )

    formatted_cnpj = fields.Char(string="CNPJ", required=True)

    @api.depends("formatted_cnpj")
    def _compute_cnpj(self):
        for record in self:
            if record.formatted_cnpj:
                record.cnpj = "".join(
                    char for char in record.formatted_cnpj if char.isalnum()
                )
            else:
                record.cnpj = False

    @api.onchange("formatted_cnpj")
    def _onchange_formatted_cnpj(self):
        for record in self:
            if record.formatted_cnpj:
                if not cnpj_cpf.validar(record.formatted_cnpj):
                    raise ValidationError("O CNPJ informado não é válido.")
                record.formatted_cnpj = cnpj_cpf.formata(
                    "".join(char for char in record.formatted_cnpj if char.isalnum())
                )

    @api.onchange("cnpj")
    def _check_cnpj(self):
        for record in self:
            if record.cnpj and len(record.cnpj) != 14:
                raise ValidationError("O CNPJ deve ter 14 caracteres.")

    phone = fields.Char(string="Telefone", size=14, required=True)

    @api.onchange("phone")
    def _onchange_phone(self):
        if self.phone:
            self.phone = format_br_phone(self.phone)

    email = fields.Char(string="Email", size=60, required=True)

    @api.onchange("email")
    def _check_email(self):
        for record in self:
            if record.email and not single_email_re.match(record.email):
                raise ValidationError("O email informado não é válido.")

    csrt_identifier = fields.Char(string="CSRT", size=2, required=True)
    csrt_hash = fields.Char(string="Hash CSRT", size=28, required=True)
