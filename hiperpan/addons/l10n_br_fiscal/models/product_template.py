# Copyright (C) 2013  Renato Lima - Akretion <renato.lima@akretion.com.br>
# License AGPL-3 - See http://www.gnu.org/licenses/agpl-3.0.html

from odoo import fields, models, api

from ..constants.fiscal import (
    NCM_FOR_SERVICE_REF,
    PRODUCT_FISCAL_TYPE,
    PRODUCT_FISCAL_TYPE_SERVICE,
    TAX_DOMAIN_ICMS,
    TAX_ICMS_OR_ISSQN,
)
from ..constants.icms import ICMS_ORIGIN, ICMS_ORIGIN_DEFAULT


class ProductTemplate(models.Model):
    _name = "product.template"
    _inherit = ["product.template", "l10n_br_fiscal.product.mixin"]

    def _get_default_ncm_id(self):
        fiscal_type = self.env.context.get("default_fiscal_type")
        if fiscal_type == PRODUCT_FISCAL_TYPE_SERVICE:
            return self.env.ref(NCM_FOR_SERVICE_REF)

    # Some modules of the repo depend on stock and have
    # demo products of type 'product' (this type is added to product.template
    # in the stock module).
    # For some reason when running the tests, some inverse method fields then fail when
    # reading 'product' value for the product type. It seems it is because
    # l10n_br_fiscal doesn't depend on stock. But we don't want such a dependency.
    # So a workaround to avoid the bug we add the 'product' value to the selection.
    type = fields.Selection(
        selection_add=[("product", "Storable Product")],
        ondelete={"product": "set consu"},
    )

    fiscal_type_id = fields.Many2one(
        comodel_name="l10n_br_fiscal.product.fiscal.type",
        string="Fiscal Type",
        company_dependent=True,
    )

    icms_origin_id = fields.Many2one(
        comodel_name="l10n_br_fiscal.icms.origin",
        string="ICMS Origin",
        company_dependent=True,
    )

    # os dois primeiros digitos do ncm 
    fiscal_genre_id = fields.Many2one(
        comodel_name="l10n_br_fiscal.ncm.genre",
        string="Fiscal NCM Genre",
        compute="_compute_fiscal_genre_id",
        store=True,
        readonly=True,
    )

    ncm_id = fields.Many2one(
        comodel_name="l10n_br_fiscal.ncm",
        index=True,
       # default=_get_default_ncm_id,
        string="NCM",
       # compute="_compute_ncm_id",
        store=True,
        readonly=False,
    )

    cest_id = fields.Many2one(
        comodel_name="l10n_br_fiscal.cest",
        index=True,
        # domain="[('ncm_ids', 'in', ncm_id)]",
        # domain=lambda self: self._get_cest_domain(),
        #domain="[('ncm_ids.code', '=like', ncm_id.code + '%')]",
        string="CEST",
    )


    @api.onchange('cest_id')
    def _onchange_cest_id(self):
        print('onchange_cest_id')
        print(self.cest_id)
        print(self.ncm_id)
        if not self.cest_id: 
            return
        if not self.ncm_id:
            self.cest_id = False
            return
        if self.cest_id and self.cest_id.ncms:
            ncm_codes = self.cest_id.ncms.split(',')
            print(ncm_codes)
            print(self.ncm_id.code_unmasked)
            if self.ncm_id.code_unmasked:
                # Check if ncm_id.code matches the beginning of any ncm_codes
                ncm_code_matches = any(
                    self.ncm_id.code_unmasked.strip().startswith(ncm_code.strip())
                    for ncm_code in ncm_codes
                )
                if not ncm_code_matches:
                    self.cest_id = False



    # @api.onchange('ncm_id')
    # def _get_cest_domain(self):
    #     print("ncm_id")
    #     print(self.ncm_id)
    #     print(type(self.ncm_id))
    #     if self.ncm_id:
    #         self.ncm_id.read(['code'])
    #         print('get_cest_domain')
    #         print(self.ncm_id.code)
        # ncm = self.env['l10n_br_fiscal.ncm'].browse(self.ncm_id)
        
        # print(ncm.code)
        # print(self.ncm_id)
        # print(self.ncm_id.code)
        # if not self.ncm_id:
        #     return [('id', '=', False)]  # Return empty domain


        # return [('ncm_ids.code', '=like', (self.ncm_id.code or "") + '%')]

        # You can customize this logic based on your needs
        # Option 1: Exact match with ncm_ids
        # return [('ncm_ids', 'in', self.ncm_id.id)]
        
        # Option 2: Partial match with ncms field using wildcards
        # This will match if the NCM code appears anywhere in the ncms string
        #return [('ncms', 'ilike', self.ncm_id.code)]
        
        # Option 2b: Using % wildcards with like operator
        # return [('ncm_ids.code', 'like', self.ncm_id.code + '%')]
        
        # Option 3: More complex wildcard matching
        # For example, if you want to match the first 4 digits: self.ncm_id.code[:4]
        # return [('ncms', 'ilike', self.ncm_id.code[:4])]

    @api.onchange('ncm_id')
    def _onchange_ncm_id(self):
        if not self.ncm_id:
            self.cest_id = False
            self.fiscal_genre_id = False
            return
        if self.cest_id and self.cest_id.ncm_ids and self.ncm_id.id not in self.cest_id.ncm_ids.ids:
            self.cest_id = False
       
    
    # nbm_id = fields.Many2one(
    #     comodel_name="l10n_br_fiscal.nbm", index=True, string="NBM"
    # )

    # tax_icms_or_issqn = fields.Selection(
    #     selection=TAX_ICMS_OR_ISSQN,
    #     string="ICMS or ISSQN Tax",
    #     default=TAX_DOMAIN_ICMS,
    #     compute="_compute_tax_icms_or_issqn",
    #     store=True,
    #     readonly=False,
    # )



    # service_type_id = fields.Many2one(
    #     comodel_name="l10n_br_fiscal.service.type",
    #     string="Service Type LC 166",
    #     domain="[('internal_type', '=', 'normal')]",
    # )

    # city_taxation_code_id = fields.Many2many(
    #     comodel_name="l10n_br_fiscal.city.taxation.code", string="City Taxation Code"
    # )

    # fiscal_genre_code = fields.Char(
    #     related="fiscal_genre_id.code",
    #     store=True,
    #     string="Fiscal Product Genre Code",
    # )

    # ipi_guideline_class_id = fields.Many2one(
    #     comodel_name="l10n_br_fiscal.tax.ipi.guideline.class",
    #     string="IPI Guideline Class",
    # )

    # ipi_control_seal_id = fields.Many2one(
    #     comodel_name="l10n_br_fiscal.tax.ipi.control.seal", string="IPI Control Seal"
    # )

    # nbs_id = fields.Many2one(
    #     comodel_name="l10n_br_fiscal.nbs", index=True, string="NBS"
    # )

    

    # uoe_id = fields.Many2one(
    #     comodel_name="uom.uom",
    #     related="ncm_id.uoe_id",
    #     store=True,
    #     string="Export UoM",
    # )

    # uoe_factor = fields.Float(string="Export UoM Factor", default=1.00)

    # uot_id = fields.Many2one(comodel_name="uom.uom", string="Tax UoM")

    # uot_factor = fields.Float(string="Tax UoM Factor")
