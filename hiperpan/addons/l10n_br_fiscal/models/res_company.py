from odoo import models, fields, api


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
