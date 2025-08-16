# Copyright (C) 2012  Renato Lima - Akretion <renato.lima@akretion.com.br>
# License AGPL-3 - See http://www.gnu.org/licenses/agpl-3.0.html

from odoo import _, fields, models

from ..constants.fiscal import TAX_DOMAIN_II, TAX_DOMAIN_IPI
#from .ibpt import get_ibpt_product


class Ncm(models.Model):
    _name = "l10n_br_fiscal.ncm"
    _inherit = [
        "l10n_br_fiscal.data.abstract",
        #  "l10n_br_fiscal.data.ncm.nbs.abstract",
        "mail.thread",
        "mail.activity.mixin",
    ]
    _description = "NCM"

    code = fields.Char(size=10)

    code_unmasked = fields.Char(size=8)

    name = fields.Char()

    exception = fields.Char(size=2)

    exception_name = fields.Char()

    tax_ipi_id = fields.Many2one(
        comodel_name="l10n_br_fiscal.tax",
        string="Tax IPI",
        domain=[("tax_domain", "=", TAX_DOMAIN_IPI)],
    )

    product_tmpl_ids = fields.One2many(
        comodel_name="product.template",
        string="Products", 
        readonly=True,
        inverse_name="ncm_id",
    )

    cest_ids = fields.Many2many(
        comodel_name="l10n_br_fiscal.cest",
        readonly=True,
        string="CESTs",
    )

    # tax_estimate_ids = fields.One2many(inverse_name="ncm_id")

    # impostos do ICMS por estado, das regulações de ICMC, não utilizado
    # tax_definition_ids = fields.Many2many(
    #     comodel_name="l10n_br_fiscal.tax.definition",
    #     readonly=True,
    #     string="Tax Definition",
    # )

    # nbm_ids = fields.Many2many(
    #     comodel_name="l10n_br_fiscal.nbm",
    #     readonly=True,
    #     string="NBMs",
    # )

    # piscofins_ids = fields.Many2many(
    #     comodel_name="l10n_br_fiscal.tax.pis.cofins",
    #     readonly=True,
    #     string="PIS/COFINS",
    # )

    _sql_constraints = [
        (
            "fiscal_ncm_code_exception_uniq",
            "unique (code, exception)",
            _("NCM already exists with this code !"),
        )
    ]

    # def _get_ibpt(self, config, code_unmasked):
    #     return get_ibpt_product(config, code_unmasked)
