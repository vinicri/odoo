"""
Wizard para criar um product.product a partir de um item da NF-e processada.

Aberto a partir do formulário do item de escrituração (botão ao lado do campo
Produto) quando o produto ainda não existe. Os campos vêm pré-populados com os
dados fiscais do item da NF-e (proc_nfe_item) para o usuário revisar e criar.
"""

import base64
import json
import logging

import requests

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
from odoo.tools.image import binary_to_image, image_process

_logger = logging.getLogger(__name__)

# Minimum resolution (in either dimension) accepted for a suggested product
# image, matching Odoo's own product image guidelines.
MIN_IMAGE_SIDE = 512
# Number of image candidates shown to the user.
MAX_IMAGE_RESULTS = 5
GOOGLE_CSE_ENDPOINT = "https://www.googleapis.com/customsearch/v1"


class DfeCreateProductWizard(models.TransientModel):
    _name = "l10n_br_dfe_monitor.create_product_wizard"
    _description = "Criar Produto"

    proc_nfe_item_id = fields.Many2one(
        "l10n_br_dfe_monitor.proc_nfe_item",
        string="Item da NF-e Processada",
        readonly=True,
    )

    # ── Image search ────────────────────────────────────────────────────
    image_1920 = fields.Image(
        string="Imagem do Produto", max_width=1920, max_height=1920
    )
    # JSON list of {"thumbnail": <url>, "image_url": <url>, "width": int,
    # "height": int} for the candidates shown to the user; not persisted
    # beyond the wizard's lifetime.
    image_search_results_json = fields.Text(readonly=True)

    # ── General (product.template) ───────────────────────────────────────
    name = fields.Char(string="Nome", required=True)
    available_in_pos = fields.Boolean(
        string="Disponível em Ponto de Venda",
        default=True,
    )
    default_code = fields.Char(string="Referência Interna")
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
        precompute=True,
        help="A storable product is a product for which you manage stock.",
    )

    @api.onchange("type")
    def compute_is_storable(self):
        if self.type == "service":
            self.is_storable = False
        else:
            self.is_storable = True

    categ_id = fields.Many2one(
        "product.category",
        string="Categoria",
        required=True,
        default=lambda self: self.env["product.template"]._get_default_category_id(),
    )

    uom_id = fields.Many2one(
        "uom.uom",
        string="Unidade de Medida",
    )

    list_price = fields.Float(
        string="Preço de Venda", digits="Product Price", default=""
    )

    # todo usar unidade de conversao pra achar o valor por unidade do estoque
    cost_price = fields.Float(
        related="proc_nfe_item_id.v_un_com",
        readonly=True,
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

    # @api.constrains("no_barcode", "barcode", "list_price", "ncm_id", "type")
    def _check_before_create(self, record):
        """Validate on save so errors show before the dialog closes (the product
        is created in the client's onRecordSaved, after this passes)."""
        barcode = (record.barcode or "").strip()
        if record.no_barcode and barcode:
            raise ValidationError(
                _(
                    "Marque 'Não possui código de barras' OU informe o "
                    "código, não ambos."
                )
            )
        if not record.no_barcode and not barcode:
            raise ValidationError(
                _(
                    "Informe o código de barras ou marque "
                    "'Não possui código de barras'."
                )
            )
        if not record.fiscal_type_id:
            raise ValidationError(_("Selecione o tipo fiscal do produto."))

        if record.list_price <= 0:
            raise ValidationError(_("O preço de venda deve ser maior que 0."))

        if not record.uom_id:
            raise ValidationError(_("Selecione a unidade de medida do produto."))

        if not record.ncm_id and record.type == "consu":
            raise ValidationError(_("Selecione o NCM do produto."))

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

        icms_origin = self.env["l10n_br_fiscal.icms.origin"].search(
            [("code", "=", proc_item.icms_orig)], limit=1
        )

        cest = self.env["l10n_br_fiscal.cest"].search(
            [("code_unmasked", "=", proc_item.cest)], limit=1
        )

        vals = {
            "proc_nfe_item_id": proc_item.id,
            "name": proc_item.x_prod,
            "ncm_id": ncm.id,
            "icms_origin_id": icms_origin.id,
            "cest_id": cest.id,
            "type": "consu",
            "is_storable": True,
        }

        return vals

    def _get_google_credentials(self):
        company = self.company_id or self.env.company
        api_key = company.dfe_google_api_key
        cx = company.dfe_google_search_cx
        if not api_key or not cx:
            raise UserError(
                _(
                    "Configure a Google API Key e o Search Engine ID (cx) na "
                    "empresa (aba 'Busca de Imagens (Google)') para buscar "
                    "imagens de produtos."
                )
            )
        return api_key, cx

    def action_search_product_images(self):
        """Search Google Images for the current ``name`` and store up to
        MAX_IMAGE_RESULTS candidates (>= MIN_IMAGE_SIDE on both dimensions) as
        JSON on ``image_search_results_json`` for the client widget to render.

        Only thumbnail/source URLs are fetched here — the full image is only
        downloaded once the user picks a candidate (action_select_product_image).
        """
        self.ensure_one()
        query = (self.name or "").strip()
        if not query:
            raise UserError(_("Informe o nome do produto antes de buscar imagens."))

        api_key, cx = self._get_google_credentials()

        try:
            response = requests.get(
                GOOGLE_CSE_ENDPOINT,
                params={
                    "key": api_key,
                    "cx": cx,
                    "q": query,
                    "searchType": "image",
                    "rights": "cc_publicdomain,cc_attribute,cc_sharealike",
                    "imgSize": "large",
                    "imgType": "photo",
                    "num": 10,
                    "safe": "active",
                },
                timeout=10,
            )
            response.raise_for_status()
            data = response.json()
        except requests.RequestException as exc:
            _logger.warning("Google image search failed for %r: %s", query, exc)
            raise UserError(_("Não foi possível buscar imagens no momento: %s") % exc)

        candidates = []
        for item in data.get("items", []):
            image_info = item.get("image") or {}
            width = image_info.get("width") or 0
            height = image_info.get("height") or 0
            if width < MIN_IMAGE_SIDE or height < MIN_IMAGE_SIDE:
                continue
            candidates.append(
                {
                    "thumbnail": image_info.get("thumbnailLink") or item.get("link"),
                    "image_url": item.get("link"),
                    "width": width,
                    "height": height,
                }
            )
            if len(candidates) >= MAX_IMAGE_RESULTS:
                break

        self.image_search_results_json = json.dumps(candidates)
        return False

    def action_select_product_image(self, image_url):
        """Download the chosen image, validate its resolution again (the
        remote source may differ from what Google reported), resize it to
        Odoo's standard product image size and store it as image_1920.
        """
        self.ensure_one()
        try:
            response = requests.get(image_url, timeout=15)
            response.raise_for_status()
        except requests.RequestException as exc:
            _logger.warning("Failed to download product image %r: %s", image_url, exc)
            raise UserError(_("Não foi possível baixar a imagem selecionada: %s") % exc)

        raw_bytes = response.content
        try:
            image = binary_to_image(raw_bytes)
            width, height = image.size
        except UserError as exc:
            raise UserError(
                _("A imagem selecionada não é válida ou está corrompida: %s") % exc
            )

        if width < MIN_IMAGE_SIDE or height < MIN_IMAGE_SIDE:
            raise UserError(
                _(
                    "A imagem selecionada (%(width)sx%(height)s) é menor que "
                    "a resolução mínima exigida (%(min)spx)."
                )
                % {"width": width, "height": height, "min": MIN_IMAGE_SIDE}
            )

        # image_process expects and returns raw bytes; Odoo Image/Binary
        # fields are written as base64, so encode only the final result.
        resized = image_process(raw_bytes, size=(1920, 1920), verify_resolution=True)
        self.image_1920 = base64.b64encode(resized)
        return False

    def action_create_product(self):
        """Create the product and store it on the wizard.

        Runs from the client's onRecordSaved, after the wizard record has been
        saved (and its constraints validated). The client reads
        ``created_product_id`` back to assign it to the escrituração item.
        """
        self.ensure_one()

        self._check_before_create(self)

        barcode = (self.barcode or "").strip()

        product = self.env["product.template"].create(
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
                "image_1920": self.image_1920 or False,
                "available_in_pos": self.available_in_pos,
            }
        )
        self.created_product_id = product.product_variant_ids[0].id
        return False
