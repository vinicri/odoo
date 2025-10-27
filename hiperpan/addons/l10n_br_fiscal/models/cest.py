from odoo import api, fields, models

from .. import tools
from ..constants.fiscal import CEST_SEGMENT
from odoo.osv import expression


class Cest(models.Model):
    _name = "l10n_br_fiscal.cest"
    _description = "CEST"

    code = fields.Char(size=9)

    name = fields.Char(required=True)

    code_unmasked = fields.Char(size=7, compute="_compute_code_unmasked", store=True)

    @api.depends("code")
    def _compute_code_unmasked(self):
        for record in self:
            record.code_unmasked = "".join(filter(str.isdigit, record.code))

    item = fields.Char(required=True)

    segment = fields.Selection(selection=CEST_SEGMENT, required=True)

    product_tmpl_ids = fields.One2many(
        comodel_name="product.template",
        string="Products",
        readonly=True,
        inverse_name="cest_id",
    )

    ncms = fields.Char(string="NCM")

    ncm_ids = fields.Many2many(
        comodel_name="l10n_br_fiscal.ncm",
        readonly=True,
        string="NCMs",
    )

    # tax_definition_ids = fields.Many2many(
    #     comodel_name="l10n_br_fiscal.tax.definition",
    #     readonly=True,
    #     string="Tax Definition",
    # )

    @api.model_create_multi
    def create(self, vals_list):
        create_super = super().create(vals_list)
        create_super.with_context(do_not_write=True).action_search_ncms()
        return create_super

    def write(self, values):
        write_super = super().write(values)
        do_not_write = self.env.context.get("do_not_write")
        if "ncms" in values.keys() and not do_not_write:
            self.with_context(do_not_write=True).action_search_ncms()
        return write_super

    def action_search_ncms(self):
        ncm = self.env["l10n_br_fiscal.ncm"]
        for r in self:
            if r.ncms:
                domain = tools.domain_field_codes(field_codes=r.ncms)
                r.ncm_ids = ncm.search(domain)

    # @api.model
    # def name_search(self, name, args=None, operator='ilike', limit=100):
    #     ncm_related = self._context.get('ncm_related')
    #     ncm_id = self._context.get('ncm_id')
    #     print('name_search')
    #     print(ncm_related)
    #     print(ncm_id)
    #     print(self.ncm_ids)
    #     if ncm_related and ncm_id:
    #         domain = args or []
    #         print(self.ncm_ids.ids)
    #         domain = expression.AND([domain, [(ncm_id, 'in', self.ncm_ids)]])
    #         return super().name_search(name, domain, operator, limit)
    #     else:
    #         return super().name_search(name, args, operator, limit)

    @api.depends("code", "name")
    def _compute_display_name(self):
        for record in self:
            record.display_name = f"{record.code} - {record.name}"

    @api.model
    def name_search(
        self,
        name,
        args=None,
        operator="ilike",
        limit=100,
    ):
        # if operator == "ilike" and not (name or "").strip():
        #     domain = []
        if operator in ("ilike", "like", "=", "=like", "=ilike"):
            domain = expression.AND(
                [
                    args or [],
                    [
                        "|",
                        "|",
                        ("name", "ilike", name),
                        ("code", "=ilike", name + "%"),
                        ("code_unmasked", "=ilike", name + "%"),
                    ],
                ]
            )
            records = self.search_fetch(domain, ["display_name"], limit=limit)
            return [(record.id, record.display_name) for record in records.sudo()]

        return super().name_search(
            name,
            args=args,
            operator=operator,
            limit=limit,
        )
