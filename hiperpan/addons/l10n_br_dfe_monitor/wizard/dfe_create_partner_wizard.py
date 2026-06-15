"""
Wizard para associar ou criar o partner emitente de uma NF-e processada.

Fluxo:
- Se já existe um res.partner com vat igual ao CNPJ/CPF do emitente, associa
  diretamente sem abrir wizard.
- Se não existe, abre o wizard com os dados do emitente pré-populados para o
  usuário revisar e criar o partner.
"""

from odoo import api, fields, models, _
from erpbrasil.base.fiscal import cnpj_cpf


class DfeCreatePartnerWizard(models.TransientModel):
    _name = "l10n_br_dfe_monitor.create_partner_wizard"
    _description = "Criar Parceiro Emitente"

    proc_nfe_id = fields.Many2one(
        "l10n_br_dfe_monitor.proc_nfe",
        string="NF-e",
        required=True,
        readonly=True,
    )

    # nfe_escrit_id = fields.Many2one(
    #     "l10n_br_dfe_monitor.dfe_nfe_escrit",
    #     string="Escrituração NF-e",
    #     readonly=True,
    # )

    company_type = fields.Selection(
        [("company", "Empresa"), ("person", "Pessoa Física")],
        string="Tipo",
        required=True,
        compute="_compute_company_type",
        default="company",
    )

    @api.depends("vat")
    def _compute_company_type(self):
        for record in self:
            if len(record.vat) == 14:
                record.company_type = "company"
            elif len(record.vat) == 11:
                record.company_type = "person"
            else:
                record.company_type = False

    # Dados pré-populados para criação do partner
    vat = fields.Char(string="CNPJ / CPF", required=True)
    legal_name = fields.Char(string="Razão Social", required=True)
    trade_name = fields.Char(string="Nome Fantasia")
    name = fields.Char(string="Nome Interno")

    street = fields.Char(string="Logradouro", required=True)
    street_number = fields.Char(string="Número", required=True)
    street_complement = fields.Char(string="Complemento")
    district = fields.Char(string="Bairro", required=True)
    zip = fields.Char(string="CEP")
    phone = fields.Char(string="Telefone")

    inscr_est = fields.Char(string="Inscrição Estadual")
    no_inscr_est = fields.Boolean(string="Não tem Inscrição Estadual")
    inscr_mun = fields.Char(string="Inscrição Municipal")
    main_cnae_id = fields.Many2one(
        comodel_name="l10n_br_fiscal.cnae",
        string="CNAE Principal",
        help="CNAE Principal da empresa.",
    )
    fiscal_framework = fields.Selection(
        [
            ("1", "Simples Nacional"),
            ("2", "Simples Nacional – excesso"),
            ("3", "Regime Normal"),
        ],
        string="Regime Fiscal",
        required=True,
    )

    # is_foreign = fields.Boolean(string="É Estrangeiro")

    # rg = fields.Char(string="RG")

    city_id = fields.Many2one("res.city", string="Cidade", required=True)
    state_id = fields.Many2one("res.country.state", string="UF", required=True)
    country_id = fields.Many2one(
        "res.country",
        string="País",
        required=True,
    )

    def action_create_partner(self):
        self.ensure_one()
        partner = self._find_partner_by_vat(self.vat)
        if not partner:
            partner = self.env["res.partner"].create(
                {
                    "company_type": self.company_type,
                    "formatted_cnpj_cpf": (
                        cnpj_cpf.formata(self.vat) if self.vat else False
                    ),
                    # Dados do Emitente
                    "name": self.name or False,
                    "legal_name": self.legal_name,
                    "trade_name": self.trade_name,
                    # Endereço
                    "street": self.street or False,
                    "street_number": self.street_number or False,
                    "street_complement": self.street_complement or False,
                    "district": self.district or False,
                    "zip": self.zip or False,
                    "phone": self.phone or False,
                    # Cadastro Fiscal
                    "inscr_est": self.inscr_est or False,
                    "no_inscr_est": self.no_inscr_est or False,
                    "inscr_mun": self.inscr_mun or False,
                    "main_cnae_id": (
                        self.main_cnae_id.id if self.main_cnae_id else False
                    ),
                    "fiscal_framework": self.fiscal_framework or False,
                    # Localização
                    "city_id": self.city_id.id if self.city_id else False,
                    "state_id": self.state_id.id if self.state_id else False,
                    "country_id": self.country_id.id if self.country_id else False,
                }
            )
        self.proc_nfe_id.link_partner(partner)

        # if self.nfe_escrit_id:
        #     self.nfe_escrit_id.partner_id = partner
        #     return {
        #         "type": "ir.actions.act_window",
        #         "name": _("Escrituração de NF-e"),
        #         "res_model": "l10n_br_dfe_monitor.dfe_nfe_escrit",
        #         "res_id": self.nfe_escrit_id.id,
        #         "view_mode": "form",
        #         "target": "new",
        #     }

        return {
            "type": "ir.actions.act_window",
            "name": _("Escrituração de NF-e"),
            "res_model": "l10n_br_dfe_monitor.dfe_nfe_escrit",
            "context": {"default_proc_nfe_id": self.proc_nfe_id.id},
            "view_mode": "form",
            "target": "new",
        }

    def _find_partner_by_vat(self, vat):
        if not vat:
            return self.env["res.partner"].browse()
        return self.env["res.partner"].search([("vat", "=", vat)], limit=1)
