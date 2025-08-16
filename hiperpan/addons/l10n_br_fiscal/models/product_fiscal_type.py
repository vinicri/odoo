from odoo import _, api, fields, models

class ProductFiscalType(models.Model):
    _name = "l10n_br_fiscal.product.fiscal.type"
    _description = "Product Fiscal Type"

    name = fields.Char(string="Name")
    code = fields.Char(string="Code", size=2, required=True)
    active = fields.Boolean(string="Active", default=True)
    product_template_ids = fields.Many2many(comodel_name="product.template", string="Products")

    _sql_constraints = [
        ('code_uniq', 'unique (code)', 'Code must be unique'),
    ]


    # def re(self):
    #    # return [(r.id, f"{r.code} - {r.name}") for r in self]
    #     return [(r.id, f"aaaa") for r in self]
    

    @api.depends("code", "name")
    def _compute_display_name(self):
        for record in self:
            record.display_name = f"{record.code} - {record.name}"