from odoo import models, fields, api


class Company(models.Model):
    _name = "res.company"
    _inherit = ["res.company", "l10n_br_base.party.mixin"]

    accountant_id = fields.Many2one(
        comodel_name="res.partner",
        string="Accountant",
        help="Accountant of the company.",
        domain="[('is_accountant', '=', True)]",
    )

    vat = fields.Char(
        compute="_compute_vat",
        inverse="_inverse_vat",
        store=True,
    )

    @api.depends("partner_id.vat")
    def _compute_vat(self):
        for company in self:
            company.vat = company.partner_id.vat

    def _inverse_vat(self):
        for company in self:
            company.partner_id.vat = company.vat

    legal_name = fields.Char(
        compute="_compute_legal_name",
        inverse="_inverse_legal_name",
        store=True,
    )

    @api.depends("partner_id.legal_name")
    def _compute_legal_name(self):
        for company in self:
            company.legal_name = company.partner_id.legal_name

    def _inverse_legal_name(self):
        for company in self:
            company.partner_id.legal_name = company.legal_name

    trade_name = fields.Char(
        compute="_compute_trade_name",
        inverse="_inverse_trade_name",
        store=True,
    )

    @api.depends("partner_id.trade_name")
    def _compute_trade_name(self):
        for company in self:
            company.trade_name = company.partner_id.trade_name

    def _inverse_trade_name(self):
        for company in self:
            company.partner_id.trade_name = company.trade_name

    formatted_cnpj_cpf = fields.Char(
        compute="_compute_formatted_cnpj_cpf",
        inverse="_inverse_formatted_cnpj_cpf",
        store=True,
    )

    @api.depends("partner_id.formatted_cnpj_cpf")
    def _compute_formatted_cnpj_cpf(self):
        for company in self:
            company.formatted_cnpj_cpf = company.partner_id.formatted_cnpj_cpf

    def _inverse_formatted_cnpj_cpf(self):
        for company in self:
            company.partner_id.formatted_cnpj_cpf = company.formatted_cnpj_cpf

    street = fields.Char(
        compute="_compute_street",
        inverse="_inverse_street",
        store=True,
    )

    @api.depends("partner_id.street")
    def _compute_street(self):
        for company in self:
            company.street = company.partner_id.street

    def _inverse_street(self):
        for company in self:
            company.partner_id.street = company.street

    street_number = fields.Char(
        compute="_compute_street_number",
        inverse="_inverse_street_number",
        store=True,
    )

    @api.depends("partner_id.street_number")
    def _compute_street_number(self):
        for company in self:
            company.street_number = company.partner_id.street_number

    def _inverse_street_number(self):
        for company in self:
            company.partner_id.street_number = company.street_number

    street_complement = fields.Char(
        compute="_compute_street_complement",
        inverse="_inverse_street_complement",
        store=True,
    )

    @api.depends("partner_id.street_complement")
    def _compute_street_complement(self):
        for company in self:
            company.street_complement = company.partner_id.street_complement

    def _inverse_street_complement(self):
        for company in self:
            company.partner_id.street_complement = company.street_complement

    district = fields.Char(
        compute="_compute_district",
        inverse="_inverse_district",
        store=True,
    )

    @api.depends("partner_id.district")
    def _compute_district(self):
        for company in self:
            company.district = company.partner_id.district

    def _inverse_district(self):
        for company in self:
            company.partner_id.district = company.district

    city_id = fields.Many2one(
        compute="_compute_city_id",
        inverse="_inverse_city_id",
        store=True,
    )

    @api.depends("partner_id.city_id")
    def _compute_city_id(self):
        for company in self:
            company.city_id = company.partner_id.city_id

    def _inverse_city_id(self):
        for company in self:
            company.partner_id.city_id = company.city_id

    inscr_est = fields.Char(
        compute="_compute_inscr_est",
        inverse="_inverse_inscr_est",
        store=True,
    )

    @api.depends("partner_id.inscr_est")
    def _compute_inscr_est(self):
        for company in self:
            company.inscr_est = company.partner_id.inscr_est

    def _inverse_inscr_est(self):
        for company in self:
            company.partner_id.inscr_est = company.inscr_est

    rg = fields.Char(
        compute="_compute_rg",
        inverse="_inverse_rg",
        store=True,
    )

    @api.depends("partner_id.rg")
    def _compute_rg(self):
        for company in self:
            company.rg = company.partner_id.rg

    def _inverse_rg(self):
        for company in self:
            company.partner_id.rg = company.rg

    inscr_mun = fields.Char(
        compute="_compute_inscr_mun",
        inverse="_inverse_inscr_mun",
        store=True,
    )

    @api.depends("partner_id.inscr_mun")
    def _compute_inscr_mun(self):
        for company in self:
            company.inscr_mun = company.partner_id.inscr_mun

    def _inverse_inscr_mun(self):
        for company in self:
            company.partner_id.inscr_mun = company.inscr_mun

    suframa = fields.Char(
        compute="_compute_suframa",
        inverse="_inverse_suframa",
        store=True,
    )

    @api.depends("partner_id.suframa")
    def _compute_suframa(self):
        for company in self:
            company.suframa = company.partner_id.suframa

    def _inverse_suframa(self):
        for company in self:
            company.partner_id.suframa = company.suframa

    is_foreign = fields.Boolean(
        compute="_compute_is_foreign",
        inverse="_inverse_is_foreign",
        store=True,
    )

    @api.depends("partner_id.is_foreign")
    def _compute_is_foreign(self):
        for company in self:
            company.is_foreign = company.partner_id.is_foreign

    def _inverse_is_foreign(self):
        for company in self:
            company.partner_id.is_foreign = company.is_foreign

    # def _get_company_address_field_names(self):
    #     """ Retorna a lista de campos que devem ser sincronizados com o partner.
    #         Ver base/models/res_company.py para implementação. """
    #     partner_fields = super()._get_company_address_field_names()
    #     return partner_fields + [
    #         "vat",
    #         "formatted_cnpj_cpf",
    #         "legal_name",
    #         "rg",
    #         "inscr_est",
    #         "inscr_mun",
    #         "district",
    #         "city_id",
    #         "suframa",
    #         "street_number",
    #         "street_complement",
    #     ]

    # validação de cnpj
    # validação de ie
