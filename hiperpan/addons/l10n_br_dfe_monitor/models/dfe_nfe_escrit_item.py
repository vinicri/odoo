from odoo import fields, models


class DfeNfeEscritItem(models.Model):
    _name = "l10n_br_dfe_monitor.dfe_nfe_escrit_item"
    _description = "Item da Escrituração de NF-e"

    dfe_nfe_escrit_id = fields.Many2one(
        "l10n_br_dfe_monitor.dfe_nfe_escrit",
        string="Escrituração de NF-e",
        required=True,
        ondelete="cascade",
    )

    proc_nfe_id = fields.Many2one(
        "l10n_br_dfe_monitor.proc_nfe",
        string="NF-e Processada",
        related="dfe_nfe_escrit_id.proc_nfe_id",
        readonly=True,
        store=True,
    )

    proc_nfe_item_id = fields.Many2one(
        "l10n_br_dfe_monitor.proc_nfe_item",
        string="Item da NF-e Processada",
        readonly=False,
        domain="[('proc_nfe_id', '=', proc_nfe_id)]",
        store=True,
    )

    item_number = fields.Integer(
        string="Nº Item", related="proc_nfe_item_id.n_item", store=True
    )

    product_id = fields.Many2one(
        "product.product",
        string="Produto",
        ondelete="set null",
    )

    def domain_icms_cst_in_tax_id(self):
        return [
            ("tax_domain_id", "=", self.env.ref("l10n_br_fiscal.tax_domain_icms").id)
        ]

    icms_cst_id = fields.Many2one(
        "l10n_br_fiscal.cst",
        string="ICMS CST",
        domain=domain_icms_cst_in_tax_id,
        ondelete="set null",
    )

    cfop_id = fields.Many2one(
        "l10n_br_fiscal.cfop",
        string="CFOP",
        ondelete="set null",
        domain="[('type_in_out', '=', 'in')]",
    )
