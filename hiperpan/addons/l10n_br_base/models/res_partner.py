from odoo import models, fields, api


class Partner(models.Model):
    _name = "res.partner"
    _inherit = ["res.partner", "l10n_br_base.party.mixin"]

    is_accountant = fields.Boolean(
        string="Is accountant?",
        help="Mark this partner as an accountant so it can be added as an accountant of a company.",
        tracking=True,
    )
    accountant_crc_code = fields.Char(
        string="CRC Code", help="CRC Code of the accountant.", tracking=True
    )

    # these two methods override the ones from address_extended/models/res_partner.py
    # we want to keep the street and street name whatever the user writes
    def _inverse_street_data(self):
        return

    def _compute_street_data(self):
        return

    @api.onchange("phone", "country_id", "company_id")
    def _onchange_phone_validation(self):
        return
