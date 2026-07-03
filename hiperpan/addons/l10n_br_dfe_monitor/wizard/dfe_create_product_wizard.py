"""
Wizard para criar um product.product a partir de um item da NF-e processada.

Aberto a partir do formulário do item de escrituração (botão ao lado do campo
Produto) quando o produto ainda não existe. Os campos vêm pré-populados com os
dados fiscais do item da NF-e (proc_nfe_item) para o usuário revisar e criar.
"""

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class DfeCreateProductWizard(models.TransientModel):
    _name = "l10n_br_dfe_monitor.create_product_wizard"
    _description = "Criar Produto"

    proc_nfe_item_id = fields.Many2one(
        "l10n_br_dfe_monitor.proc_nfe_item",
        string="Item da NF-e Processada",
        readonly=True,
    )

    name = fields.Char(string="Nome", required=True)
    default_code = fields.Char(string="Código Interno")
    barcode = fields.Char(string="GTIN / Código de Barras")
    ncm_id = fields.Many2one(
        "l10n_br_fiscal.ncm",
        string="NCM",
        required=True,
    )
    uom_id = fields.Many2one(
        "uom.uom",
        string="Unidade de Medida",
        required=True,
    )
    icms_origin_id = fields.Many2one(
        "l10n_br_fiscal.icms.origin",
        string="Origem da Mercadoria",
        required=True,
    )
    fiscal_type_id = fields.Many2one(
        "l10n_br_fiscal.product.fiscal.type",
        string="Tipo Fiscal",
        required=True,
    )

    # Set after creation so the client can read back the new product and assign
    # it to the (possibly unsaved) escrituração item.
    created_product_id = fields.Many2one(
        "product.product",
        string="Produto Criado",
        readonly=True,
    )

    @api.model
    def default_get_from_item(self, proc_nfe_item_id):
        """Build the wizard default values from a processed NF-e item.

        Returns a values dict suitable for ``create`` (used by the client to
        open the wizard pre-populated for an unsaved escrituração item).
        """
        proc_item = self.env["l10n_br_dfe_monitor.proc_nfe_item"].browse(
            proc_nfe_item_id
        )
        if not proc_item:
            return {}

        ncm = self.env["l10n_br_fiscal.ncm"].search(
            [("code_unmasked", "=", proc_item.ncm)], limit=1
        )
        # uom = self.env["uom.uom"].search(
        #     [("nfe_name", "=", proc_item.u_com)], limit=1
        # )
        # if not uom:
        #     uom = self.env["uom.uom"].search(
        #         [("dfe_uom_name_ids.name", "=", proc_item.u_com)], limit=1
        #     )
        icms_origin = self.env["l10n_br_fiscal.icms.origin"].search(
            [("code", "=", proc_item.icms_orig)], limit=1
        )
        return {
            "proc_nfe_item_id": proc_item.id,
            "name": proc_item.x_prod,
            # "default_code": proc_item.c_prod,
            # "barcode": proc_item.c_ean or False,
            "ncm_id": ncm.id,
            # "uom_id": uom.id,
            "icms_origin_id": icms_origin.id,
        }

    def action_create_product(self):
        """Create the product.product and store it on the wizard.

        The record is saved by the dialog before this runs, so the client reads
        ``created_product_id`` back to assign it to the escrituração item. The
        button carries ``close="1"`` so only the wizard dialog closes.
        """
        self.ensure_one()
        if not self.ncm_id:
            raise UserError(_("Informe o NCM do produto."))
        if not self.uom_id:
            raise UserError(_("Informe a Unidade de Medida do produto."))

        # The barcode must be a GTIN of 8/12/13/14 digits; otherwise the product
        # is created without one (no_barcode) to satisfy the fiscal constraint.
        barcode = (self.barcode or "").strip()
        valid_barcode = barcode.isdigit() and len(barcode) in (8, 12, 13, 14)

        product = self.env["product.product"].create(
            {
                "name": self.name,
                "default_code": self.default_code or False,
                "barcode": barcode if valid_barcode else False,
                "no_barcode": not valid_barcode,
                "ncm_id": self.ncm_id.id,
                "uom_id": self.uom_id.id,
                "uom_po_id": self.uom_id.id,
                "icms_origin_id": self.icms_origin_id.id,
                "fiscal_type_id": self.fiscal_type_id.id,
            }
        )
        self.created_product_id = product.id
        return False
