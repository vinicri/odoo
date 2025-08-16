from odoo import models, fields, api
from erpbrasil.base import misc
from erpbrasil.base.fiscal import cnpj_cpf
import re
import string


class PartyMixin(models.AbstractModel):
    _name = "l10n_br_base.party.mixin"
    _description = "Brazilian partner and company mixin"

    # razao social ou nome completo
    legal_name = fields.Char(
        size=256,
        help="Used in fiscal documents",
        tracking=True,
    )

    # Nome Fantasia
    trade_name = fields.Char(
        size=256,
        help="Nome fantasia",
        tracking=True,
    )

    # CNPJ/CPF sem caracteres especiais
    vat = fields.Char(
        string="CNPJ/CPF Stripped",
        help="CNPJ/CPF without special characters",
        compute="_compute_cnpj_cpf_stripped",
        store=True,
        index=True,
        tracking=True,
    )

    # CNPJ/CPF com caracteres especiais
    formatted_cnpj_cpf = fields.Char(
        string="CNPJ/CPF",
        size=18,
        tracking=True,
    )

    street = fields.Char(
        string="Logadouro",
        size=60,
        compute="_compute_street",
        inverse="_inverse_street",
        store=True,
        readonly=False,
        tracking=True,
    )

    def _compute_street(self):
        return

    def _inverse_street(self):
        return

    street_number = fields.Char(
        string="Número",
        compute="_compute_street_number",
        inverse="_inverse_street_number",
        size=60,
        tracking=True,
        readonly=False,
        store=True,
    )

    def _compute_street_number(self):
        return

    def _inverse_street_number(self):
        return

    street_complement = fields.Char(
        string="Complemento",
        size=60,
        tracking=True,
    )

    district = fields.Char(
        string="Bairro",
        size=128,
        tracking=True,
    )

    city_id = fields.Many2one(
        string="Cidade",
        comodel_name="res.city",
        domain="[('state_id', '=', state_id), ('ibge_code', '!=', False)]",
        tracking=True,
    )

    # uf, CEP, codigo País, nome País, telefine

    # inscricao estadual sem formatação
    inscr_est = fields.Char(
        string="Inscrição Estadual",
        size=14,
        tracking=True,
    )

    rg = fields.Char(
        string="RG",
        tracking=True,
    )

    inscr_mun = fields.Char(
        string="Inscrição Municipal",
        size=18,
        tracking=True,
    )

    suframa = fields.Char(
        string="SUFRAMA",
        size=18,
        unaccent=False,
        tracking=True,
    )

    is_foreign = fields.Boolean(
        string="É Estrangeiro",
        help="Mark this partner as a foreign partner",
        tracking=True,
    )

    unformatted_zip = fields.Char(
        string="CEP sem formatação",
        compute="_compute_unformatted_zip",
        tracking=True,
    )

    phone = fields.Char(
        string="Telefone",
        compute="_compute_phone",
        inverse="_inverse_phone",
        readonly=False,
        store=True,
        tracking=True,
    )

    @api.onchange("phone", "country_id")
    def _compute_phone(self):
        if self.country_id.code == "BR":
            self.phone = self._format_br_phone(self.phone)
        else:
            self.phone = False

    def _format_br_phone(self, phone):
        if phone:
            val = re.sub("[^0-9]", "", phone)
            if len(val) == 10:
                return "%s %s-%s" % (val[0:2], val[2:6], val[6:10])
            elif len(val) == 11:
                return "%s %s-%s" % (val[0:2], val[2:7], val[7:11])
            else:
                return False

    def _inverse_phone(self):
        return

    @api.depends("zip")
    def _compute_unformatted_zip(self):
        for record in self:
            if record.zip:
                record.unformatted_zip = re.sub("[^0-9]", "", record.zip)
            else:
                record.unformatted_zip = False

    # l10n_br_base_state_id = fields.Many2one(
    #     string="State of Address",
    #     comodel_name="res.country.state",
    #     domain="[('country_id', '=', l10n_br_base_country_id), ('l10n_br_base_ibge_code', '!=', False)]",
    # )

    # l10n_br_base_country_id = fields.Many2one(
    #     comodel_name="res.country",
    #     default=lambda self: self.env.ref("base.br"),
    # )

    @api.depends("formatted_cnpj_cpf")
    def _compute_cnpj_cpf_stripped(self):
        for record in self:
            if record.formatted_cnpj_cpf:
                record.vat = "".join(
                    char for char in record.formatted_cnpj_cpf if char.isalnum()
                )
            else:
                record.vat = False

    @api.onchange("formatted_cnpj_cpf")
    def _onchange_cnpj_cpf(self):
        self.formatted_cnpj_cpf = cnpj_cpf.formata(str(self.formatted_cnpj_cpf))

    @api.onchange("zip")
    def _onchange_zip(self):
        if self.country_id.code == "BR":
            self.zip = self._format_br_zipcode(self.zip)

    @api.onchange("state_id")
    def _onchange_state_id(self):
        self.city_id = None

    @api.onchange("city_id")
    def _onchange_city_id(self):
        self.city = self.city_id.name

    @api.onchange("name")
    def _onchange_name(self):
        if self.legal_name == False:
            self.legal_name = self.name

    def _format_br_zipcode(self, zipcode):
        if zipcode:
            val = re.sub("[^0-9]", "", zipcode)
            if len(val) == 8:
                return "%s-%s" % (val[0:5], val[5:8])
        return False
