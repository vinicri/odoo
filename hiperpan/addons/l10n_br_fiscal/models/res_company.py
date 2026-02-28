from odoo import _, models, fields, api
from odoo.exceptions import ValidationError


class Company(models.Model):
    _name = "res.company"
    _inherit = ["res.company", "l10n_br_fiscal.party.mixin"]

    fiscal_framework = fields.Selection(
        compute="_compute_fiscal_framework",
        inverse="_inverse_fiscal_framework",
        store=True,
    )

    ipi_contributes = fields.Boolean(
        compute="_compute_ipi_contributes",
        inverse="_inverse_ipi_contributes",
        store=True,
    )

    regular_framework_type = fields.Selection(
        compute="_compute_regular_framework_type",
        inverse="_inverse_regular_framework_type",
        store=True,
    )

    @api.depends("partner_id.regular_framework_type")
    def _compute_regular_framework_type(self):
        for company in self:
            company.regular_framework_type = company.partner_id.regular_framework_type

    def _inverse_regular_framework_type(self):
        for company in self:
            company.partner_id.regular_framework_type = company.regular_framework_type

    @api.constrains("fiscal_framework", "regular_framework_type")
    def _check_regular_framework_type(self):
        for record in self:
            if record.fiscal_framework == "3" and not record.regular_framework_type:
                raise ValidationError(
                    _(
                        "O campo 'Tipo de regime normal' é obrigatório para o Regime Normal."
                    )
                )
            elif record.fiscal_framework != "3" and record.regular_framework_type:
                raise ValidationError(
                    _(
                        "O campo 'Tipo de regime normal' não pode ser preenchido para o Simples Nacional."
                    )
                )

    @api.depends("partner_id.fiscal_framework")
    def _compute_fiscal_framework(self):
        for company in self:
            company.fiscal_framework = company.partner_id.fiscal_framework  # or "3"

    def _inverse_fiscal_framework(self):
        for company in self:
            company.partner_id.fiscal_framework = company.fiscal_framework

    @api.depends("partner_id.ipi_contributes")
    def _compute_ipi_contributes(self):
        for company in self:
            company.ipi_contributes = company.partner_id.ipi_contributes

    def _inverse_ipi_contributes(self):
        for company in self:
            company.partner_id.ipi_contributes = company.ipi_contributes
