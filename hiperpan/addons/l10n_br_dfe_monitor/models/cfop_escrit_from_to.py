from odoo import api, fields, models

# Outbound CFOP first digit -> inbound CFOP first digit
CFOP_FROM_TO_PREFIX = {
    "3": "1",
    "6": "2",
    "7": "3",
}


class CfopEscritFromTo(models.Model):
    _name = "l10n_br_dfe_monitor.cfop_escrit_from_to"
    _description = "CFOP Escrit From To"

    cfop_id_from = fields.Many2one(
        comodel_name="l10n_br_fiscal.cfop",
        string="CFOP From",
        domain="[('type_in_out', '=', 'out')]",
        required=True,
    )

    cfop_id_from_code = fields.Char(
        string="CFOP From Code",
        related="cfop_id_from.code",
    )

    cfop_to_code_prefix = fields.Char(
        compute="_compute_cfop_to_code_prefix",
    )

    cfop_id_to = fields.Many2one(
        comodel_name="l10n_br_fiscal.cfop",
        string="CFOP To",
        domain="[('code', '=like', cfop_to_code_prefix + '%')]",
        required=True,
    )

    active = fields.Boolean(string="Active", default=True)

    @api.depends("cfop_id_from_code")
    def _compute_cfop_to_code_prefix(self):
        for record in self:
            first = (record.cfop_id_from_code or "")[:1]
            record.cfop_to_code_prefix = CFOP_FROM_TO_PREFIX.get(first) or ""

    @api.onchange("cfop_id_from")
    def _onchange_cfop_id_from(self):
        self.cfop_id_to = False
