from odoo import models, fields, api
from erpbrasil.base import misc
from erpbrasil.base.fiscal import cnpj_cpf

class PartyMixin(models.AbstractModel):
    _name = 'l10n_br_base.party.mixin'
    _description = 'Brazilian partner and company mixin'


    # l10n_br_base_legal_name = fields.Char(
    #     string="Legal Name",
    #     size=128,
    #     help="Used in fiscal documents",
    # )


    l10n_br_base_cnpj_cpf_stripped = fields.Char(
        string="CNPJ/CPF Stripped",
        help="CNPJ/CPF without special characters",
        compute="_compute_cnpj_cpf_stripped",
        store=True,
        index=True,
    )

    l10n_br_base_cnpj_cpf = fields.Char(
        string="CNPJ/CPF",
        size=18,
    )

    l10n_br_base_inscr_est = fields.Char(
        string="State Tax Number",
        size=17,
    )

    l10n_br_base_rg = fields.Char(
        string="RG",
    )


    l10n_br_base_inscr_mun = fields.Char(
        string="Municipal Tax Number",
        size=18,
    )

    l10n_br_base_city_id = fields.Many2one(
        string="City of Address",
        comodel_name="res.city",
        domain="[('state_id', '=', l10n_br_base_state_id), ('l10n_br_base_ibge_code', '!=', False)]", 
    )

    l10n_br_base_state_id = fields.Many2one(
        string="State of Address",
        comodel_name="res.country.state",
        domain="[('country_id', '=', l10n_br_base_country_id), ('l10n_br_base_ibge_code', '!=', False)]",
    )

    l10n_br_base_country_id = fields.Many2one(
        comodel_name="res.country",
        default=lambda self: self.env.ref("base.br"),
    )

    @api.depends("l10n_br_base_cnpj_cpf")
    def _compute_cnpj_cpf_stripped(self):
        for record in self:
            if record.l10n_br_base_cnpj_cpf:
                record.l10n_br_base_cnpj_cpf_stripped = "".join(
                    char for char in record.l10n_br_base_cnpj_cpf if char.isalnum()
                )
            else:
                record.l10n_br_base_cnpj_cpf_stripped = False

    @api.onchange("l10n_br_base_cnpj_cpf")
    def _onchange_cnpj_cpf(self):
        self.l10n_br_base_cnpj_cpf = cnpj_cpf.formata(str(self.l10n_br_base_cnpj_cpf))