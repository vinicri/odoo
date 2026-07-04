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

    # ── General (product.template) ───────────────────────────────────────
    name = fields.Char(string="Nome", required=True)
    # default_code is an Integer on this product.template (Referência Interna).
    default_code = fields.Integer(string="Referência Interna")
    barcode = fields.Char(string="Código de Barras")
    no_barcode = fields.Boolean(string="Não possui código de barras")

    type = fields.Selection(
        [
            ("consu", "Mercadoria"),
            ("service", "Serviço"),
            ("combo", "Combo"),
        ],
        string="Tipo de Produto",
        required=True,
        default="consu",
    )

    is_storable = fields.Boolean(
        "Estocado",
        store=True,
        compute="compute_is_storable",
        readonly=False,
        default=False,
        precompute=True,
        help="A storable product is a product for which you manage stock.",
    )

    @api.depends("type")
    def compute_is_storable(self):
        self.filtered(lambda t: t.type != "consu" and t.is_storable).is_storable = False
        self.filtered(lambda t: t.type == "consu" and t.is_storable).is_storable = True

    categ_id = fields.Many2one(
        "product.category",
        string="Categoria",
        required=True,
        default=lambda self: self.env["product.template"]._get_default_category_id(),
    )

    uom_id = fields.Many2one(
        "uom.uom",
        string="Unidade de Medida",
        required=True,
        default=lambda self: self.env.ref("uom.product_uom_unit", False),
    )

    list_price = fields.Float(
        string="Preço de Venda",
        digits="Product Price",
        default=1.0,
    )

    company_id = fields.Many2one(
        "res.company",
        string="Empresa",
    )

    # ── Fiscal Information (l10n_br_fiscal.product.mixin) ─────────────────
    fiscal_type_id = fields.Many2one(
        "l10n_br_fiscal.product.fiscal.type",
        string="Tipo Fiscal",
    )
    icms_origin_id = fields.Many2one(
        "l10n_br_fiscal.icms.origin",
        string="Origem da Mercadoria",
    )
    ncm_id = fields.Many2one(
        "l10n_br_fiscal.ncm",
        string="NCM",
    )
    # CEST is restricted to the ones linked to the selected NCM, mirroring the
    # product form's behavior.
    cest_id = fields.Many2one(
        "l10n_br_fiscal.cest",
        string="CEST",
        domain="[('ncm_ids', '=', ncm_id)]",
    )
    fiscal_additional_information = fields.Text(
        string="Informações adicionais de produto para documento fiscal",
    )

    # Set after creation so the client can read back the new product and assign
    # it to the (possibly unsaved) escrituração item.
    created_product_id = fields.Many2one(
        "product.product",
        string="Produto Criado",
        readonly=True,
    )

    @api.onchange("ncm_id")
    def _onchange_ncm_id(self):
        """Clear the CEST when it no longer matches the selected NCM."""
        for record in self:
            if record.cest_id and record.ncm_id not in record.cest_id.ncm_ids:
                record.cest_id = False

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
        uom = self.env["uom.uom"].search([("nfe_name", "=", proc_item.u_com)], limit=1)
        if not uom:
            uom = self.env["uom.uom"].search(
                [("dfe_uom_name_ids.name", "=", proc_item.u_com)], limit=1
            )
        icms_origin = self.env["l10n_br_fiscal.icms.origin"].search(
            [("code", "=", proc_item.icms_orig)], limit=1
        )

        vals = {
            "proc_nfe_item_id": proc_item.id,
            "name": proc_item.x_prod,
            "ncm_id": ncm.id,
            "icms_origin_id": icms_origin.id,
        }

        if uom:
            vals["uom_id"] = uom.id

        return vals

    def action_create_product(self):
        """Create the product.product and store it on the wizard.

        The record is saved by the dialog before this runs, so the client reads
        ``created_product_id`` back to assign it to the escrituração item.
        """
        self.ensure_one()

        # Respect the product.template barcode constraint: barcode XOR
        # no_barcode, and one of them is required.
        barcode = (self.barcode or "").strip()
        if self.no_barcode and barcode:
            raise UserError(
                _(
                    "Marque 'Não possui código de barras' OU informe o código, não ambos."
                )
            )
        if not self.no_barcode and not barcode:
            raise UserError(
                _(
                    "Informe o código de barras ou marque "
                    "'Não possui código de barras'."
                )
            )

        if not self.fiscal_type_id:
            raise UserError(_("Selecione o tipo fiscal do produto."))

        if not self.icms_origin_id:
            raise UserError(_("Selecione a origem da mercadoria."))

        if not self.ncm_id and self.type == "consu":
            raise UserError(_("Selecione o NCM do produto."))

        product = self.env["product.product"].create(
            {
                "name": self.name,
                "default_code": self.default_code or False,
                "barcode": barcode or False,
                "no_barcode": self.no_barcode,
                "type": self.type,
                "is_storable": self.is_storable,
                "categ_id": self.categ_id.id,
                "uom_id": self.uom_id.id,
                "uom_po_id": self.uom_id.id,
                "list_price": self.list_price,
                "company_id": self.company_id.id or False,
                "fiscal_type_id": self.fiscal_type_id.id,
                "icms_origin_id": self.icms_origin_id.id,
                "ncm_id": self.ncm_id.id,
                "cest_id": self.cest_id.id or False,
                "fiscal_additional_information": (
                    self.fiscal_additional_information or False
                ),
            }
        )
        self.created_product_id = product.id
        return False
