from odoo import fields, models


class ProductGenre(models.Model):
    _name = "l10n_br_fiscal.ncm.genre"
    _inherit = [
      "l10n_br_fiscal.data.abstract",
      "mail.thread",
      "mail.activity.mixin",
    ]
    _description = "NCM Product Genre"

    product_tmpl_ids = fields.One2many(
        comodel_name="product.template",
        string="Products", 
        readonly=True,
        inverse_name="ncm_id",
    )



