from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

ALLOWED_BOM_FISCAL_TYPES = ("03", "04")


class MrpBom(models.Model):
    _inherit = "mrp.bom"

    is_default_bom_for_product = fields.Boolean(
        string="Lista de Materiais Padrão para o Produto",
        default=False,
    )

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records.filtered("is_default_bom_for_product")._unset_other_defaults()
        return records

    def write(self, vals):
        res = super().write(vals)
        if vals.get("is_default_bom_for_product"):
            self._unset_other_defaults()
        return res

    def _unset_other_defaults(self):
        for bom in self:
            siblings = self.search(
                [
                    ("product_tmpl_id", "=", bom.product_tmpl_id.id),
                    ("is_default_bom_for_product", "=", True),
                    ("id", "!=", bom.id),
                ]
            )
            if siblings:
                siblings.write({"is_default_bom_for_product": False})

    @api.constrains("product_tmpl_id", "company_id")
    def _check_fiscal_type_for_br_company(self):
        for bom in self:
            if bom.company_id.country_id.code != "BR":
                continue
            fiscal_type = (
                bom.product_id.fiscal_type_id
                if bom.product_id
                else bom.product_tmpl_id.fiscal_type_id
            )
            if fiscal_type.code not in ALLOWED_BOM_FISCAL_TYPES:
                raise ValidationError(
                    _(
                        "The product '%(product)s' has fiscal type '%(fiscal_type)s'. "
                        "For Brazilian companies, only products with fiscal type "
                        "'03 - Produto em Processo' or '04 - Produto Acabado' "
                        "can have a Bill of Materials.",
                        product=bom.product_tmpl_id.display_name,
                        fiscal_type=fiscal_type.display_name,
                    )
                )

    def unlink(self):
        for bom in self:
            if bom.company_id.country_id.code != "BR":
                continue
            template = bom.product_tmpl_id
            remaining = template.bom_ids - bom
            if (
                not remaining
                and template.fiscal_type_id.code in ALLOWED_BOM_FISCAL_TYPES
            ):
                raise ValidationError(
                    _(
                        "Não é possível excluir a última Ficha Técnica (Bill of Materials) do produto '%(product)s'. "
                        "Produtos com tipo fiscal '03 - Produto em Processo' ou "
                        "'04 - Produto Acabado' devem possuir ao menos uma Ficha Técnica cadastrada.",
                        product=template.display_name,
                    )
                )
        return super().unlink()
