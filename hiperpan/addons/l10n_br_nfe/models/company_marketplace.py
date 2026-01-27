from odoo import models, fields, api
from odoo.exceptions import ValidationError


class CompanyMarketplace(models.Model):
    _name = "l10n_br_nfe.company.marketplace"
    _description = "Company Marketplace"

    name = fields.Char(string="Nome", compute="_compute_name", store=True)

    company_id = fields.Many2one(comodel_name="res.company", string="Empresa")

    provider_id = fields.Many2one(
        comodel_name="res.partner",
        string="Provedor",
        domain="[('is_marketplace_provider', '=', True)]",
        required=True,
    )

    marketplace_username = fields.Char(string="Usuário do Marketplace", required=True)

    @api.depends("company_id", "company_id.name", "marketplace_username")
    def _compute_name(self):
        for record in self:
            parts = []
            if record.company_id and record.company_id.name:
                parts.append(record.company_id.name)
            if record.marketplace_username:
                parts.append(record.marketplace_username)
            record.name = " - ".join(parts) if parts else False

    @api.constrains("provider_id")
    def _check_provider_id(self):
        for record in self:
            if (
                record.provider_id
            ):  # Se o provedor de marketplace for alterado, o usuário do marketplace deve ser alterado
                if not record.provider_id.vat or len(record.provider_id.vat) != 14:
                    raise ValidationError(
                        "O CNPJ do provedor de marketplace é obrigatório e deve ter 14 caracteres."
                    )

    @api.onchange("provider_id")
    def _onchange_provider_id(self):
        for record in self:
            if record.provider_id:
                record.marketplace_username = False
