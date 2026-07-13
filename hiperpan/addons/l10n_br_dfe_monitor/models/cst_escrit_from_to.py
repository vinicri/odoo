from odoo import api, fields, models


class CstEscritFromTo(models.Model):
    _name = "l10n_br_dfe_monitor.cst_escrit_from_to"
    _description = "CST Escrit From To"

    cst_id_from = fields.Many2one(
        comodel_name="l10n_br_fiscal.cst",
        string="CST From",
        required=True,
        domain="[('cst_type', 'in', ('out', 'all'))]",
    )

    cst_id_from_tax_domain_id = fields.Many2one(
        related="cst_id_from.tax_domain_id",
    )

    cst_id_to_tax_domain_id = fields.Many2one(
        comodel_name="l10n_br_fiscal.tax.domain",
        compute="_compute_cst_id_to_tax_domain_id",
    )

    cst_id_to = fields.Many2one(
        comodel_name="l10n_br_fiscal.cst",
        string="CST To",
        required=True,
        domain="[('tax_domain_id', '=', cst_id_to_tax_domain_id), ('cst_type', 'in', ('in', 'all'))]",
    )

    active = fields.Boolean(string="Active", default=True)

    @api.depends("cst_id_from_tax_domain_id")
    def _compute_cst_id_to_tax_domain_id(self):
        tax_domain_icmssn = self.env.ref("l10n_br_fiscal.tax_domain_icmssn")
        tax_domain_icms = self.env.ref("l10n_br_fiscal.tax_domain_icms")
        for record in self:
            if record.cst_id_from_tax_domain_id == tax_domain_icmssn:
                record.cst_id_to_tax_domain_id = tax_domain_icms
            else:
                record.cst_id_to_tax_domain_id = record.cst_id_from_tax_domain_id

    @api.onchange("cst_id_from")
    def _onchange_cst_id_from(self):
        self.cst_id_to = False
