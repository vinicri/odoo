from odoo import fields, models, api


class DfeNfeEscritItemDefaults(models.Model):
    _name = "l10n_br_dfe_monitor.dfe_nfe_escrit_item_defaults"
    _description = "Defaults for Items of Escrituração de NF-e"

    gtin = fields.Char(string="GTIN", size=14)
    cod_prod = fields.Char(string="Código do Produto", size=60)

    unit_text = fields.Char(string="Unidade de Medida", size=6)

    description = fields.Char(string="Descrição", size=120)

    cnpj = fields.Char(string="CNPJ", size=14)

    partner_id = fields.Many2one(
        "res.partner",
        string="Fornecedor",
        ondelete="set null",
    )

    product_id = fields.Many2one(
        "product.product",
        string="Produto",
        ondelete="set null",
    )

    uom_id = fields.Many2one(
        "uom.uom",
        string="Unidade de Medida",
        ondelete="set null",
    )

    own_use = fields.Boolean(string="Own Use and Consumption", default=False)

    cfop_id = fields.Many2one(
        "l10n_br_fiscal.cfop",
        string="CFOP",
        ondelete="set null",
        domain="[('type_in_out', '=', 'in')]",
    )

    icms_cst_id = fields.Many2one(
        "l10n_br_fiscal.cst",
        string="ICMS CST",
        ondelete="set null",
    )

    ipi_cst_id = fields.Many2one(
        "l10n_br_fiscal.cst",
        string="IPI CST",
        ondelete="set null",
    )

    pis_cst_id = fields.Many2one(
        "l10n_br_fiscal.cst",
        string="PIS CST",
        ondelete="set null",
    )

    cofins_cst_id = fields.Many2one(
        "l10n_br_fiscal.cst",
        string="COFINS CST",
        ondelete="set null",
    )
