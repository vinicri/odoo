import logging
from tkinter import EW

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError

# from odoo.addons.queue_job.job import job

from .constants import (
    DESTINATION_ID,
    NFE_DOCUMENT_MODEL,
    NFE_EMISSION_FINALITY,
    NFCE_VALID_CFOPS,
    NFE_OPERATION_TYPE,
)

CFOP_IN_OUT = [("in", _("In")), ("out", _("Out"))]

from ..utils.ibpt import (
    get_ibpt_product_taxes,
    calculate_approximate_taxes,
    IBPTError,
)

_logger = logging.getLogger(__name__)

# Fields that trigger IBPT re-fetch when changed
IBPT_TRIGGER_FIELDS = {
    "product_id",
    "product_description",
    "unit",
    "total_value",
    "gtin",
    "icms_origin",
}


class NFeDocumentLine(models.Model):
    _name = "l10n_br_nfe.nfe.document.line"
    _description = "Itens da Nota Fiscal Eletrônica"
    _order = "item_number asc"

    nfe_id = fields.Many2one(
        comodel_name="l10n_br_nfe.nfe.document",
        string="NF-e",
        required=True,
        ondelete="cascade",
    )

    is_debug_mode = fields.Boolean(string="Debug mode", default=True, store=False)

    product_id = fields.Many2one("product.product", string="Produto", required=True)

    # Número do item (1-990). Sequencial.
    item_number = fields.Integer(string="Número do Item", required=True, readonly=True)

    @api.model
    def create(self, vals):
        """Automatically assign sequential item numbers when creating new lines"""
        if vals.get("nfe_id") and not vals.get("item_number"):
            # Get the next available item number for this NFE document
            max_item_number = self.search(
                [("nfe_id", "=", vals["nfe_id"])], order="item_number desc", limit=1
            )

            if max_item_number:
                vals["item_number"] = max_item_number.item_number + 1
            else:
                vals["item_number"] = 1

        record = super().create(vals)

        # # Trigger IBPT fetch in background
        # if record.product_id:
        #     record.with_delay()._job_fetch_ibpt_taxes()

        return record

    def write(self, vals):
        res = super().write(vals)
        # # Trigger IBPT fetch in background when relevant fields change
        # if any(field in vals for field in IBPT_TRIGGER_FIELDS):
        #     for record in self:
        #         if record.product_id:
        # record.with_delay()._job_fetch_ibpt_taxes()
        return res

    @api.model
    def _reorder_item_numbers(self, nfe_id):
        """Reorder item numbers for a specific NFE document to ensure sequential numbering"""
        lines = self.search([("nfe_id", "=", nfe_id)], order="id asc")

        for index, line in enumerate(lines, 1):
            if line.item_number != index:
                line.item_number = index

    # Codigo interno. Preencher com CFOP, caso se trate de itens não
    # relacionados com mercadorias/produtos e que o contribuinte não
    # possua codificação própria. Formato: “CFOP9999”.
    product_code = fields.Char(
        string="Código do Produto",
        readonly=True,
        # required=True,
        # default="CFOP9999",
        store=True,
        size=60,
        compute="_compute_product_code",
    )

    @api.depends("product_id", "product_id.default_code")
    def _compute_product_code(self):
        for record in self:
            if record.product_id:
                if record.product_id.default_code:
                    record.product_code = record.product_id.default_code
                else:
                    record.product_code = "CFOP9999"
            else:
                record.product_code = False

    @api.constrains("product_code")
    def _check_product_code(self):
        for record in self:
            if not record.product_code:
                raise ValidationError(_("O Código do Produto é obrigatório."))

    # Preencher com o código GTIN-8, GTIN-12, GTIN-13 ou GTIN-14 (antigos códigos EAN, UPC e DUN-14)
    # Para produtos que não possuem código de barras com GTIN, deve ser informado o literal “SEM GTIN”
    gtin = fields.Char(
        compute="_compute_gtin",
        string="Código de Barras",
        store=True,
        size=14,
        readonly=True,
    )

    @api.depends("product_id.barcode", "product_id.no_barcode")
    def _compute_gtin(self):
        for record in self:
            if record.product_id.no_barcode:
                record.gtin = "SEM GTIN"
            elif record.product_id.barcode:
                record.gtin = record.product_id.barcode
            else:
                record.gtin = False

    @api.constrains("gtin", "product_id.no_barcode")
    def _check_gtin(self):
        for record in self:
            if not record.product_id.no_barcode and not record.gtin:
                raise ValidationError(
                    _(
                        "Item %s. O produto não está marcado como 'Não possui código de barras' mas o código de barras não foi informado."
                        % record.product_description
                    )
                )
            if record.product_id.no_barcode and (
                record.product_id.barcode or record.gtin != "SEM GTIN"
            ):
                raise ValidationError(
                    _(
                        "Item %s. O produto está marcado como 'Não possui código de barras' mas o código de barras foi informado."
                        % record.product_description
                    )
                )
            if record.gtin and len(record.gtin) not in (8, 12, 13, 14):
                raise ValidationError(
                    _(
                        "Item %s. O Código de Barras deve ter 8, 12, 13 ou 14 caracteres."
                        % record.product_description
                    )
                )

    # Descrição do produto ou serviço.
    # Para NFC-e em homologação, a descrição do primeiro item deve ser "NOTA FISCAL EMITIDA EM AMBIENTE DE HOMOLOGACAO - SEM VALOR FISCAL".
    product_description = fields.Char(
        # related="product_id.name",
        string="Descrição do Produto",
        size=120,
        store=True,
        compute="_compute_product_description",
    )

    @api.depends("product_id.name")
    def _compute_product_description(self):
        for record in self:
            if record.product_id:
                # Get the product name in Brazilian Portuguese
                record.product_description = record.product_id.with_context(
                    lang="pt_BR"
                ).name
            else:
                record.product_description = False

    @api.constrains("product_description")
    def _check_product_description(self):
        for record in self:
            if not record.product_description:
                raise ValidationError(_("A Descrição do Produto é obrigatória."))

    # Código NCM com 8 dígitos. Obrigatório.
    # Para serviço ou item sem produto, informar “00” (dois zeros)
    ncm_code = fields.Char(
        related="product_id.ncm_id.code",
        string="NCM",
        # required=True,
        store=True,
        readonly=True,
    )

    ncm_unmasked = fields.Char(
        related="product_id.ncm_id.code_unmasked",
        string="NCM sem pontuação",
        store=True,
        readonly=True,
    )

    # TODO o codigo nem sempre é obrigatório
    # Em caso de item de serviço ou item que não tenham produto (ex. transferência de crédito, crédito do ativo imobilizado, etc.), informar o valor 00 (dois zeros). (NT 2014/004)
    @api.constrains("ncm_code")
    def _check_ncm_code(self):
        for record in self:
            if not record.ncm_code:
                raise ValidationError(
                    _(
                        "Item %s: O Código NCM é obrigatório."
                        % record.product_description
                    )
                )

    @api.constrains("ncm_unmasked")
    def _check_ncm_unmasked(self):
        for record in self:
            if record.ncm_unmasked and len(record.ncm_unmasked) != 8:
                raise ValidationError(
                    _(
                        "Item %s: O Código NCM deve ter 8 dígitos."
                        % record.product_description
                    )
                )

    # Código CEST (Código Especificador da Substituição Tributária). Opcional.
    # cest é obrigatório para os CST/CSONS com substituição tributária, mas essa validação está a cargo da SEFAZ no momento
    cest_code = fields.Char(
        related="product_id.cest_id.code",
        string="CEST",
        size=7,
        store=True,
        readonly=True,
    )

    # Código Fiscal de Operações e Prestações. Usar Tabela de CFOP.
    # NFC-e (mod=65) aceita unicamente CFOPs específicos de venda a consumidor final.
    # CFOP de Entrada para NF-e de Saída é facultativo (pode ser rejeitado).
    cfop_type_in_out = fields.Char(
        string="Tipo Entrada/Saída CFOP",
        compute="_compute_cfop_type_in_out",
        readonly=True,
    )

    @api.depends("operation_nature_id")
    def _compute_cfop_type_in_out(self):
        """Map operation type to CFOP type_in_out:
        - Operation type '0' (Entrada) -> 'in'
        - Operation type '1' (Saída) -> 'out'
        """
        for record in self:
            if record.operation_nature_id:
                if record.operation_nature_id.type == "0":
                    record.cfop_type_in_out = "in"
                elif record.operation_nature_id.type == "1":
                    record.cfop_type_in_out = "out"
                else:
                    record.cfop_type_in_out = False
            else:
                record.cfop_type_in_out = False

    cfop_code_like = fields.Char(
        string="CFOP Like",
        compute="_compute_cfop_code_like",
        readonly=True,
    )

    @api.depends("destination_id", "operation_nature_id")
    def _compute_cfop_code_like(self):
        for record in self:
            if record.destination_id:
                if record.operation_nature_id.type == "0":
                    if record.destination_id == "1":
                        record.cfop_code_like = "1%"
                    elif record.destination_id == "2":
                        record.cfop_code_like = "2%"
                    elif record.destination_id == "3":
                        record.cfop_code_like = "3%"
                elif record.operation_nature_id.type == "1":
                    if record.destination_id == "1":
                        record.cfop_code_like = "5%"
                    elif record.destination_id == "2":
                        record.cfop_code_like = "6%"
                    elif record.destination_id == "3":
                        record.cfop_code_like = "7%"
                else:
                    record.cfop_code_like = False
            else:
                record.cfop_code_like = False

    allowed_cfop_ids = fields.Many2many(
        comodel_name="l10n_br_fiscal.cfop",
        string="Allowed CFOPs",
        compute="_compute_allowed_cfop_ids",
    )

    @api.depends("document_model", "cfop_type_in_out", "cfop_code_like")
    def _compute_allowed_cfop_ids(self):
        Cfop = self.env["l10n_br_fiscal.cfop"]
        for record in self:
            base_domain = [
                ("ind_nfe", "=", "1"),
                ("type_in_out", "=", record.cfop_type_in_out),
            ]
            if record.cfop_code_like:
                base_domain.append(("code", "=like", record.cfop_code_like))

            if record.document_model == "65":
                base_domain.append(("code", "in", NFCE_VALID_CFOPS))

            if record.emission_finality == "4":
                base_domain.append("|")
                base_domain.append(("ind_devol", "=", "1"))
                base_domain.append(("code", "in", ["1949", "2949"]))

            if record.emission_finality in ("1", "3"):
                base_domain.append(("ind_devol", "=", "0"))

            record.allowed_cfop_ids = Cfop.search(base_domain)

    cfop_code_id = fields.Many2one(
        comodel_name="l10n_br_fiscal.cfop",
        string="CFOP",
        required=True,
        domain="[('id', 'in', allowed_cfop_ids)]",
    )

    cfop_code = fields.Char(
        related="cfop_code_id.code",
        string="Código CFOP",
        store=True,
    )

    @api.constrains("cfop_code", "document_model")
    def _check_cfop_code(self):
        for record in self:
            if not record.cfop_code:
                raise ValidationError(
                    _(
                        "Item %s: O Código CFOP é obrigatório."
                        % record.product_description
                    )
                )
            if len(record.cfop_code) != 4:
                raise ValidationError(
                    _(
                        "Item %s: O Código CFOP deve ter 4 dígitos."
                        % record.product_description
                    )
                )
            # Rejeição 794: NFC-e (modelo 65) com CFOP inválido
            if (
                record.document_model == "65"
                and record.cfop_code not in NFCE_VALID_CFOPS
            ):
                raise ValidationError(
                    _("Item %s: CFOP %s inválido para NFC-e. " "CFOPs válidos: %s")
                    % (
                        record.product_description,
                        record.cfop_code,
                        ", ".join(NFCE_VALID_CFOPS),
                    )
                )

    # Unidade Comercial. Informar a unidade de comercialização do produto.
    # NFC-e com unidade de comercialização inválida é rejeitada.
    unit = fields.Char(
        related="product_id.uom_id.nfe_name",
        string="Unidade de Venda",
        readonly=True,
        size=6,
        store=True,
    )

    @api.constrains("unit")
    def _check_unit(self):
        for record in self:
            if not record.unit:
                raise ValidationError(
                    _(
                        "A Unidade de Venda é obrigatória. Informe a unidade de comercialização no cadastro do produto."
                    )
                )

    # Informar a quantidade de comercialização do produto.
    quantity = fields.Float(
        string="Quantidade de Venda", required=True, digits=(11, 4), default=1
    )

    @api.constrains("quantity")
    def _check_quantity(self):
        for record in self:
            if not record.quantity:
                raise ValidationError(_("A Quantidade de Venda é obrigatória."))
            elif record.quantity < 0:
                raise ValidationError(
                    _("A Quantidade de Venda deve ser maior ou igual a 0.")
                )

    @api.onchange("quantity")
    def _onchange_quantity(self):
        if self.quantity < 0:
            self.quantity = 0
            return {
                "warning": {
                    "title": "Valor inválido",
                    "message": "A quantidade deve ser maior que zero.",
                }
            }

    # Valor Unitário de Comercialização do produto, informativo (0-10 decimais). [48, 49]
    unit_price = fields.Float(
        string="Valor Unitário",
        readonly=False,
        required=True,
        digits=(11, 2),
    )

    @api.constrains("unit_price")
    def _check_unit_price(self):
        for record in self:
            if not record.unit_price:
                raise ValidationError(_("O Valor Unitário é obrigatório."))
            elif record.unit_price < 0:
                raise ValidationError(
                    _("O Valor Unitário deve ser maior ou igual a 0.")
                )

    is_production_fiscal_type = fields.Boolean(
        compute="_compute_is_production_fiscal_type",
        store=False,
    )

    @api.depends("product_id", "product_id.fiscal_type_id")
    def _compute_is_production_fiscal_type(self):
        for record in self:
            record.is_production_fiscal_type = (
                record.product_id.fiscal_type_id.code == "04"
            )

    @api.onchange("product_id")
    def _onchange_product_id(self):
        for record in self:
            if record.product_id:
                price_dict = record.product_id._price_compute("list_price")
                record.unit_price = price_dict.get(record.product_id.id)
            else:
                record.unit_price = False
            record.include_ipi_in_icms_bc = False

    @api.onchange("unit_price")
    def _onchange_unit_price(self):
        for record in self:
            if record.unit_price and record.unit_price < 0:
                record.unit_price = 0
                return {
                    "warning": {
                        "title": _("Aviso"),
                        "message": _("O Valor Unitário deve ser maior ou igual a 0."),
                    }
                }

    unit_discount_value = fields.Float(
        string="Valor de desconto por unidade",
        digits=(11, 6),
        compute="_compute_unit_discount_value",
        store=True,
        readonly=False,
    )

    @api.depends("unit_price", "unit_discount_percent")
    def _compute_unit_discount_value(self):
        if self.env.context.get("skip_discount_compute"):
            return
        for record in self:
            record.unit_discount_value = (
                record.unit_price * record.unit_discount_percent / 100
            )

    @api.onchange("unit_discount_value")
    def _check_unit_discount_value(self):
        for record in self:
            if record.unit_discount_value > record.unit_price:
                # Set both values to break the circular dependency cycle
                record.unit_discount_percent = 0
                record.unit_discount_value = 0
                return {
                    "warning": {
                        "title": _("Aviso"),
                        "message": _(
                            "O Valor de Desconto por Unidade deve ser menor ou igual ao Valor Unitário."
                        ),
                    }
                }

    @api.constrains("unit_discount_value")
    def _check_unit_discount_value(self):
        for record in self:
            if record.unit_discount_value > record.unit_price:
                raise ValidationError(
                    _(
                        "O Valor de Desconto por Unidade deve ser menor ou igual ao Valor Unitário."
                    )
                )
            elif record.unit_discount_value < 0:
                raise ValidationError(
                    _("O Valor de Desconto por Unidade deve ser maior ou igual a 0.")
                )

    unit_discount_percent = fields.Float(
        string="Percentual de desconto por unidade",
        digits=(3, 4),
        compute="_compute_unit_discount_percent",
        store=True,
        readonly=False,
    )

    @api.depends("unit_price", "unit_discount_value")
    def _compute_unit_discount_percent(self):
        if self.env.context.get("skip_discount_compute"):
            return
        for record in self:
            if record.unit_price:
                record.unit_discount_percent = (
                    record.unit_discount_value / record.unit_price * 100
                )

    @api.onchange("unit_discount_percent")
    def _onchange_unit_discount_percent(self):
        for record in self:
            if record.unit_discount_percent > 100:
                # Set both values to break the circular dependency cycle
                record.unit_discount_value = 0
                record.unit_discount_percent = 0
                return {
                    "warning": {
                        "title": _("Aviso"),
                        "message": _(
                            "O Percentual de Desconto por Unidade deve ser menor ou igual a 100%."
                        ),
                    }
                }

    @api.constrains("unit_discount_percent")
    def _check_unit_discount_percent(self):
        for record in self:
            if record.unit_discount_percent > 100:
                raise ValidationError(
                    _(
                        "O Percentual de Desconto por Unidade deve ser menor ou igual a 100%."
                    )
                )
            elif record.unit_discount_percent < 0:
                raise ValidationError(
                    _(
                        "O Percentual de Desconto por Unidade deve ser maior ou igual a 0%."
                    )
                )

    # Valor Total Bruto do Produto/Serviço.
    # Somente o valor do produto vezes a quantidade. Não inclui o valor do desconto, do frete, do seguro, etc.
    total_value = fields.Float(
        compute="_compute_total_value",
        string="Valor Total Bruto do Produto/Serviço",
        # required=True,
        digits=(13, 2),
        readonly=True,
        store=True,
    )

    @api.depends("unit_price", "quantity")
    def _compute_total_value(self):
        for record in self:
            record.total_value = record.unit_price * record.quantity

    @api.constrains("total_value")
    def _check_total_value(self):
        for record in self:
            if not record.total_value:
                raise ValidationError(
                    _("O Valor Total Bruto do Produto/Serviço é obrigatório.")
                )
            if record.total_value < 0:
                raise ValidationError(
                    _(
                        "O Valor Total Bruto do Produto/Serviço deve ser maior ou igual a 0."
                    )
                )

    # O GTIN da unidade tributável deve corresponder àquele da menor unidade comercializável identificada por código GTIN.
    # Para produtos que não possuem código de barras com GTIN, deve ser informado o literal "SEM GTIN”
    # Obrigatório.
    gtin_trib = fields.Char(
        compute="_compute_gtin_trib",
        string="GTIN da Unidade Tributável",
        store=True,
        size=14,
        readonly=True,
    )

    @api.depends("gtin")
    def _compute_gtin_trib(self):
        for record in self:
            record.gtin_trib = record.gtin

    @api.constrains("gtin_trib")
    def _check_gtin_trib(self):
        for record in self:
            if not record.gtin_trib:
                raise ValidationError(_("O GTIN da Unidade Tributável é obrigatório."))

    # Unidade Tributável. Obrigatório.
    unit_trib = fields.Char(
        related="product_id.uom_id.nfe_name",
        string="Unidade Tributável",
        readonly=True,
        size=6,
        store=True,
    )

    @api.constrains("unit_trib")
    def _check_unit_trib(self):
        for record in self:
            if not record.unit_trib:
                raise ValidationError(_("A Unidade Tributável é obrigatória."))

    # Quantidade Tributável. Obrigatório.
    quantity_trib = fields.Float(
        string="Quantidade Tributável",
        compute="_compute_quantity_trib",
        readonly=True,
        digits=(11, 4),
    )

    @api.constrains("quantity_trib")
    def _check_quantity_trib(self):
        for record in self:
            if not record.quantity_trib:
                raise ValidationError(_("A Quantidade Tributável é obrigatória."))

    @api.depends("quantity")
    def _compute_quantity_trib(self):
        for record in self:
            record.quantity_trib = record.quantity

    unit_value_trib = fields.Float(
        string="Valor Unitário",
        readonly=True,
        digits=(11, 10),
        compute="_compute_unit_value_trib",
    )

    @api.constrains("unit_value_trib")
    def _check_unit_value_trib(self):
        for record in self:
            if not record.unit_value_trib:
                raise ValidationError(_("O Valor Unitário Tributável é obrigatório."))

    @api.depends("unit_price")
    def _compute_unit_value_trib(self):
        for record in self:
            record.unit_value_trib = record.unit_price

    # Valor Total do Frete do item. Opcional.
    freight_value = fields.Float(string="Valor do Frete do Item", digits=(13, 2))

    # Valor Total do Seguro do item. Opcional.
    insurance_value = fields.Float(string="Valor do Seguro do Item", digits=(13, 2))

    # Valor do Desconto do item. Opcional.
    discount_value = fields.Float(
        string="Valor do Desconto",
        digits=(13, 2),
        store=True,
        compute="_compute_discount_value",
    )

    @api.depends("unit_discount_value", "quantity")
    def _compute_discount_value(self):
        for record in self:
            record.discount_value = record.unit_discount_value * record.quantity

    # Outras despesas acessórias do item. Opcional.
    other_expenses_value = fields.Float(
        string="Outras Despesas Acessórias do Item", digits=(13, 2)
    )

    # Indica se valor do Item entra no valor total da NF-e.
    include_in_total = fields.Selection(
        [
            ("0", "Não compõe o valor total da NF-e"),
            ("1", "Compõe o valor total da NF-e"),
        ],
        string="Incluir no Total da NF-e",
        required=True,
        default="1",
    )

    # esse campo vem do contexto do documento fiscal, do nfe_document xml view.
    issuer_id = fields.Many2one(
        comodel_name="res.partner",
        string="Emitente",
        readonly=True,
    )

    operation_nature_id = fields.Many2one(
        comodel_name="l10n_br_nfe.nfe.operation_nature",
        string="Natureza da Operação",
        readonly=True,
    )

    operation_type = fields.Selection(
        NFE_OPERATION_TYPE,
        string="Tipo de Operação",
        readonly=True,
    )

    destination_id = fields.Selection(
        DESTINATION_ID,
        string="Identificador de Local de Destino",
        readonly=True,
    )

    document_model = fields.Selection(
        NFE_DOCUMENT_MODEL,
        string="Modelo do Documento Fiscal",
        readonly=True,
    )

    # esse campo vem do contexto do documento fiscal, do nfe_document xml view.
    emission_finality = fields.Selection(
        NFE_EMISSION_FINALITY,
        string="Finalidade da Emissão",
        readonly=True,
    )

    def _is_issuer_simples_nacional(self):
        return self.issuer_id.fiscal_framework in ("1", "2")

    def _issuer_contributes_to_ipi(self):
        return self.issuer_id.ipi_contributes

    is_simples_nacional = fields.Boolean(
        string="Simples Nacional",
        compute="_compute_is_simples_nacional",
        readonly=True,
    )

    @api.depends("issuer_id", "issuer_id.fiscal_framework")
    def _compute_is_simples_nacional(self):
        for record in self:
            record.is_simples_nacional = record._is_issuer_simples_nacional()

    issuer_contributes_to_ipi = fields.Boolean(
        string="Contribui com IPI",
        compute="_compute_issuer_contributes_to_ipi",
        readonly=True,
    )

    @api.depends("issuer_id", "issuer_id.ipi_contributes")
    def _compute_issuer_contributes_to_ipi(self):
        for record in self:
            record.issuer_contributes_to_ipi = record.issuer_id.ipi_contributes

    # ===  impostos ===

    icms_allowed_tax_group_ids = fields.Many2many(
        comodel_name="l10n_br_fiscal.tax.group",
        string="Grupos de Imposto ICMS Permitidos",
        compute="_compute_icms_allowed_tax_group_ids",
    )

    # 1 - Simples Nacional,
    # 2 - Simples Nacional – excesso de sublimite da receita bruta
    # 3 - Regime Normal
    @api.depends("issuer_id", "issuer_id.fiscal_framework", "emission_finality")
    def _compute_icms_allowed_tax_group_ids(self):
        tax_group_icmssn = self.env.ref("l10n_br_fiscal.tax_group_icmssn")
        tax_group_icms = self.env.ref("l10n_br_fiscal.tax_group_icms")
        for record in self:
            if record.emission_finality == "4":
                # Devolução: permite tanto ICMSSN quanto ICMS
                record.icms_allowed_tax_group_ids = tax_group_icms | tax_group_icmssn
            elif not record.issuer_id or not record.issuer_id.fiscal_framework:
                record.icms_allowed_tax_group_ids = False  # empty recordset
            elif record.is_simples_nacional:
                record.icms_allowed_tax_group_ids = tax_group_icmssn
            else:
                record.icms_allowed_tax_group_ids = tax_group_icms

    # === ICMS ===

    icms_origin = fields.Char(
        related="product_id.icms_origin_id.code",
        string="Origem da Mercadoria",
        size=1,
        store=True,
        readonly=True,
    )

    @api.constrains("icms_origin")
    def _check_icms_origin(self):
        for record in self:
            if not record.icms_origin:
                raise ValidationError(_("A Origem da Mercadoria é obrigatória."))
            if record.icms_origin not in ("0", "1", "2", "3", "4", "5", "6", "7", "8"):
                raise ValidationError(_("A Origem da Mercadoria é inválida."))

    icms_tax_id = fields.Many2one(
        comodel_name="l10n_br_fiscal.tax",
        string="Imposto",
        domain="[('tax_group_id', 'in', icms_allowed_tax_group_ids)]",
        required=True,
    )

    @api.constrains("icms_tax_id")
    def _check_icms_tax_id(self):
        for record in self:
            if not record.icms_tax_id:
                raise ValidationError(
                    _(
                        f"O ICMS não foi informado para o item da nota fiscal: {record.product_description}."
                    )
                )
            if (
                record.nfe_id.issuer_id.fiscal_framework in ("1", "2")
                and record.icms_tax_id.tax_group_id.id
                != self.env.ref("l10n_br_fiscal.tax_group_icmssn").id
                and record.emission_finality != "4"
            ):
                raise ValidationError(
                    _(
                        f"O ICMS informado para o produto {record.product_description} é invalido para regime fiscal da empresa emitente (Simples Nacional)."
                    )
                )
            if (
                record.nfe_id.issuer_id.fiscal_framework not in ("1", "2")
                and record.icms_tax_id.tax_group_id.id
                != self.env.ref("l10n_br_fiscal.tax_group_icms").id
                and record.emission_finality != "4"
            ):
                raise ValidationError(
                    _(
                        f"O ICMS informado para o produto {record.product_description} é invalido para regime fiscal da empresa emitente (Regime Normal)."
                    )
                )

    icms_cst_id = fields.Many2one(
        related="icms_tax_id.cst_out_id",
        string="CST ICMS",
        readonly=True,
        store=True,
    )

    @api.constrains("icms_cst_id")
    def _check_icms_cst_id(self):
        for record in self:
            if not record.icms_cst_id:
                raise ValidationError(
                    _(
                        f"O CST do ICMS é invalido para o item da nota fiscal: {record.product_description}."
                    )
                )

    icms_cst_code = fields.Char(
        related="icms_cst_id.code",
        string="CST ICMS",
        store=True,
        readonly=True,
    )

    @api.constrains("icms_cst_code")
    def _check_icms_cst_code(self):
        for record in self:
            if not record.icms_cst_code:
                raise ValidationError(
                    _(
                        f"O código do CST do ICMS é invalido para o item da nota fiscal: {record.product_description}."
                    )
                )

    # devolucao de simples nacional csosn 900
    # descatar o icms da nota de entrada pra empresa poder tomar o credito
    #  Na emissão de devolução por NF-e a base de cálculo e o ICMS porventura destacada na nota fiscal de compra, serão indicados nos campos próprios da NF-e.
    # • O CSOSN da nota fiscal de devolução de mercadorias será o 900.
    # • Q ICMS ST será informado no campo "Outras despesas acessórias")e nos Dados Adicionais que o valor discriminado em despesas acessórias trata-se de ICMS ST/ (Consulta COPAT 96/14
    # - verificar na legislação estadual).
    # • O IPI será informado na nota fiscal de devolução no campo de Informações Complementares
    # e no campo de "IPI Devolvido"
    icms_cst = fields.Char(
        compute="_compute_icms_cst",
        string="CST ICMS",
        store=True,
        readonly=True,
    )

    @api.depends("icms_cst_id", "icms_origin")
    def _compute_icms_cst(self):
        for record in self:
            if record.icms_origin and record.icms_cst_id:
                record.icms_cst = f"{record.icms_origin}{record.icms_cst_id.code}"
            else:
                record.icms_cst = False

    @api.constrains("icms_cst")
    def _check_icms_cst(self):
        for record in self:
            if not record.icms_cst:
                raise ValidationError(
                    _(
                        f"O CST do ICMS não foi informado para o item da nota fiscal: {record.product_description}."
                    )
                )

    has_icms_own_operation = fields.Boolean(
        string="Modalidade da Base de Calculo Permitida",
        compute="_compute_has_icms_own_operation",
    )

    @api.depends("icms_cst_code")
    def _compute_has_icms_own_operation(self):
        for record in self:
            record.has_icms_own_operation = record.icms_cst_code in (
                "00",
                "10",
                "20",
                "51",
                "70",
                "90",
                "900",
            )

    # todo colocar na definicao do imposto tax (talvez nao)
    icms_bc_modality = fields.Selection(
        string="Modalidade da Base de Calculo",
        selection=[
            ("0", "Margem Valor Agregado (%)"),
            ("1", "Pauta (valor)"),
            ("2", "Preço Tabelado Máximo (valor)"),
            ("3", "Valor da Operação"),
        ],
        compute="_compute_icms_bc_modality",
        readonly=False,
        store=True,
    )

    @api.depends("icms_cst_code")
    def _compute_icms_bc_modality(self):
        for record in self:
            if record.icms_cst_code in (
                "101",
                "102",
                "103",
                "201",
                "202",
                "203",
                "300",
                "400",
                "500",
                "900",
            ):
                record.icms_bc_modality = False
            # 30 - isenta ou nao tributada com cobrança de ICMS por ST
            # 40 - isenta
            # 41 - nao tributada
            # 50 - suspensao
            # 60 - tributada anteriormente por ST
            elif record.icms_cst_code in ("30", "40", "41", "50", "51", "60", "90"):
                record.icms_bc_modality = False
            elif record.icms_cst_code in ("00", "10", "20", "70"):
                record.icms_bc_modality = "0"

    @api.constrains("icms_bc_modality")
    def _check_icms_bc_modality(self):
        for record in self:
            if (
                record.icms_cst_code
                in (
                    "101",
                    "102",
                    "103",
                    "201",
                    "202",
                    "203",
                    "300",
                    "400",
                    "500",
                )
                and record.icms_bc_modality
            ):
                raise ValidationError(
                    _(
                        f"O CSOSN {record.icms_cst_code} não admite informar a modalidade da base de calculo do ICMS para o item da nota fiscal: {record.product_description}."
                    )
                )
            # todo adicionar os csts em que é obrigatório informar a modalidade da base de calculo
            if not record.icms_bc_modality and record.icms_cst_code in (
                "00",
                "10",
                "20",
                "70",
            ):
                raise ValidationError(
                    _(
                        f"A modalidade da base de calculo do ICMS deve ser informada para o item da nota fiscal quando o CST for {record.icms_cst_code}: {record.product_description}."
                    )
                )

    include_ipi_in_icms_bc = fields.Boolean(
        string="Incluir IPI na BC do ICMS",
        default=False,
    )

    is_icms_cst_90_900 = fields.Boolean(
        string="É CST 90 ou 900",
        compute="_compute_is_icms_cst_90_900",
    )

    @api.depends("icms_cst_code")
    def _compute_is_icms_cst_90_900(self):
        for record in self:
            record.is_icms_cst_90_900 = record.icms_cst_code in ("90", "900")

    icms_bc_value = fields.Float(
        string="Valor da Base de Calculo",
        digits=(13, 2),
        compute="_compute_icms_bc_value",
        store=True,
        readonly=True,
    )

    # ainda não cobre a base de calculo da importação
    @api.depends(
        "has_icms_own_operation",
        "icms_cst_code",
        "icms_bc_reduction_percent",
        "total_value",
        "freight_value",
        "insurance_value",
        "other_expenses_value",
        "discount_value",
        "ipi_value",
        "include_ipi_in_icms_bc",
    )
    def _compute_icms_bc_value(self):
        for record in self:
            if not record.has_icms_own_operation:
                record.icms_bc_value = 0
            else:
                ipi_value = record.ipi_value if record.include_ipi_in_icms_bc else 0
                standard_base = (
                    record.total_value
                    + record.freight_value
                    + record.insurance_value
                    + record.other_expenses_value
                    - record.discount_value
                    + ipi_value
                )
                if record.icms_cst_code in ("00", "10"):
                    record.icms_bc_value = standard_base
                elif record.icms_cst_code in ("20", "70", "51", "90", "900"):
                    record.icms_bc_value = (
                        standard_base * (1 - record.icms_bc_reduction_percent / 100)
                        if record.icms_bc_reduction_percent
                        else standard_base
                    )
                else:
                    record.icms_bc_value = 0

    @api.constrains("icms_bc_value")
    def _check_icms_bc_value(self):
        for record in self:
            if (
                record.icms_cst_code
                in ("101", "102", "103", "201", "202", "203", "300", "400", "500")
                and record.icms_bc_value
            ):
                raise ValidationError(
                    _(
                        f"O CSOSN {record.icms_cst_code} não admite informar o valor da base de calculo do ICMS para o item da nota fiscal: {record.product_description}."
                    )
                )
            # 30 - isenta ou nao tributada com cobrança de ICMS por ST
            # 40 - isenta
            # 41 - nao tributada
            # 50 - suspensao
            # 60 - tributada anteriormente por ST
            elif (
                record.icms_cst_code in ("30", "40", "41", "50", "60")
                and record.icms_bc_modality
            ):
                raise ValidationError(
                    _(
                        f"O ICMS CST {record.icms_cst_code} não admite informar a modalidade da base de calculo do ICMS para o item da nota fiscal: {record.product_description}."
                    )
                )
            if record.icms_bc_value < 0:
                raise ValidationError(
                    _(
                        f"O valor da base de calculo do ICMS é invalido para o item da nota fiscal: {record.product_description}."
                    )
                )

    # TODO para o ICMS calculado, deve ser implementado
    # @api.depends(
    #     "total_value",
    #     "freight_value",
    #     "insurance_value",
    #     "other_expenses_value",
    #     "discount_value",
    # )
    # def _compute_icms_bc_value(self):
    #     for record in self:
    #         record.icms_bc_value = (
    #             record.total_value
    #             + record.freight_value
    #             + record.insurance_value
    #             + record.other_expenses_value
    #             - record.discount_value
    #         )

    is_icms_base_reduction_allowed = fields.Boolean(
        string="Permitido redução da base de calculo do ICMS",
        compute="_compute_is_icms_cst_20_70",
    )

    @api.depends("icms_cst_code")
    def _compute_is_icms_cst_20_70(self):
        for record in self:
            record.is_icms_base_reduction_allowed = record.icms_cst_code in (
                "20",
                "70",
                "51",
                "90",
                "900",
            )

    icms_bc_reduction_percent = fields.Float(
        string="Percentual de Redução da Base de Calculo",
        digits=(3, 4),
        compute="_compute_icms_bc_reduction_percent",
        store=True,
        readonly=False,
    )

    @api.depends("is_icms_base_reduction_allowed")
    def _compute_icms_bc_reduction_percent(self):
        for record in self:
            if not record.is_icms_base_reduction_allowed:
                record.icms_bc_reduction_percent = False

    @api.constrains("is_icms_base_reduction_allowed")
    def _check_icms_bc_reduction_percent(self):
        for record in self:
            if (
                record.icms_bc_reduction_percent
                and not record.is_icms_base_reduction_allowed
            ):
                raise ValidationError(
                    _(
                        f"O ICMS CST {record.icms_cst_code} não admite informar o percentual de redução da base de calculo do ICMS para o item da nota fiscal: {record.product_description}."
                    )
                )
            # 20 - Com redução de base de cálculo
            # 70 - Com redução de BC e cobrança de ICMS por ST
            elif (
                record.icms_cst_code in ("20", "70")
                and not record.icms_bc_reduction_percent
            ):
                raise ValidationError(
                    _(
                        f"Para o ICMS CST {record.icms_cst_code} é obrigatório informar o percentual de redução da base de calculo do ICMS para o item da nota fiscal: {record.product_description}."
                    )
                )
            elif (
                record.icms_bc_reduction_percent
                and record.icms_bc_reduction_percent <= 0
            ):
                raise ValidationError(
                    _(
                        f"O percentual de redução da base de calculo do ICMS é invalido para o item da nota fiscal: {record.product_description}."
                    )
                )

    icms_tax_percent = fields.Float(
        related="icms_tax_id.percent_amount",
        string="Aliquota",
        digits=(3, 4),
        readonly=True,
        store=True,
    )

    @api.constrains("icms_tax_percent", "icms_cst_code")
    def _check_icms_tax_percent(self):
        for record in self:
            if (
                record.icms_cst_code
                in ("101", "102", "103", "201", "202", "203", "300", "400", "500")
                and record.icms_tax_percent
            ):
                raise ValidationError(
                    _(
                        f"O CSOSN {record.icms_cst_code} não admite informar a aliquota do ICMS para o item da nota fiscal: {record.product_description}."
                    )
                )
            # 30 - isenta ou nao tributada com cobrança de ICMS por ST
            # 40 - isenta
            # 41 - nao tributada
            # 50 - suspensao
            # 60 - tributada anteriormente por ST
            elif (
                record.icms_cst_code in ("30", "40", "41", "50", "60")
                and record.icms_tax_percent
            ):
                raise ValidationError(
                    _(
                        f"O ICMS CST {record.icms_cst_code} não admite informar a aliquota do ICMS para o item da nota fiscal: {record.product_description}."
                    )
                )
            # 00 - Tributada integralmente
            # 10 - Tributada e com cobrança do ICMS por substituição tributária
            # 20 - Com redução de base de cálculo
            # 70 - Com redução de BC e cobrança de ICMS por ST
            elif (
                record.icms_cst_code in ("00", "10", "20", "70")
                and not record.icms_tax_percent
            ):
                raise ValidationError(
                    _(
                        f"Para o ICMS CST {record.icms_cst_code} falta a aliquota do ICMS para o item da nota fiscal: {record.product_description}."
                    )
                )
            elif record.icms_tax_percent and record.icms_tax_percent <= 0:
                raise ValidationError(
                    _(
                        f"A aliquota do ICMS é invalido para o item da nota fiscal: {record.product_description}."
                    )
                )

    is_deferment_cst = fields.Boolean(
        string="É CST com Diferimento",
        compute="_compute_is_deferment_cst",
    )

    @api.depends("icms_cst_code")
    def _compute_is_deferment_cst(self):
        for record in self:
            record.is_deferment_cst = record.icms_cst_code == "51"

    icms_deferment_percent = fields.Float(
        string="Percentual de Diferimento", digits=(3, 4)
    )

    @api.onchange("icms_cst_code", "icms_deferment_percent")
    def _onchange_icms_deferment_percent(self):
        for record in self:
            if record.icms_cst_code != "51":
                record.icms_deferment_percent = False

    # 51 tributação com diferimento
    @api.constrains("icms_deferment_percent")
    def _check_icms_deferment_percent(self):
        for record in self:
            if record.icms_cst_code != "51" and record.icms_deferment_percent:
                raise ValidationError(
                    _(
                        f"O CSOSN {record.icms_cst_code} não admite informar o percentual de diferimento do ICMS para o item da nota fiscal: {record.product_description}."
                    )
                )

            elif record.icms_deferment_percent and (
                record.icms_deferment_percent <= 0
                or record.icms_deferment_percent > 100
            ):
                raise ValidationError(
                    _(
                        f"O percentual de diferimento do ICMS é invalido para o item da nota fiscal: {record.product_description}."
                    )
                )

    icms_deferment_value = fields.Float(
        string="Valor do Diferimento",
        digits=(13, 2),
        compute="_compute_icms_deferment_value",
        readonly=False,
        store=True,
    )

    @api.depends("icms_cst_code", "icms_deferment_value")
    def _compute_icms_deferment_value(self):
        for record in self:
            if record.icms_cst_code == "51":
                record.icms_deferment_value = (
                    record.icms_value * record.icms_deferment_percent / 100
                )
            else:
                record.icms_deferment_value = False

    @api.constrains("icms_deferment_value", "icms_cst_code")
    def _check_icms_deferment_value(self):
        for record in self:
            if record.icms_cst_code == "51" and record.icms_deferment_value:
                raise ValidationError(
                    _(
                        f"O CSOSN {record.icms_cst_code} não admite informar o valor do diferimento do ICMS para o item da nota fiscal: {record.product_description}."
                    )
                )
            elif record.icms_deferment_value and record.icms_deferment_value <= 0:
                raise ValidationError(
                    _(
                        f"O valor do diferimento do ICMS é invalido para o item da nota fiscal: {record.product_description}."
                    )
                )

    icms_deferment_payable = fields.Float(
        string="Valor do ICMS Diferido",
        digits=(13, 2),
        compute="_compute_icms_deferment_payable",
        readonly=False,
        store=True,
    )

    @api.depends("icms_value", "icms_deferment_value")
    def _compute_icms_deferment_payable(self):
        for record in self:
            record.icms_deferment_payable = (
                record.icms_value - record.icms_deferment_value
            )

    icms_value = fields.Float(
        string="Valor do ICMS",
        digits=(13, 2),
        compute="_compute_icms_value",
        readonly=False,
        store=True,
    )

    @api.depends("icms_bc_value", "icms_tax_percent")
    def _compute_icms_value(self):
        for record in self:
            # 00 - Tributada integralmente
            # 10 - Tributada e com cobrança do ICMS por substituição tributária
            # 20 - Com redução de base de cálculo
            # 70 - Com redução de BC e cobrança de ICMS por ST
            # 51 - tributação com diferimento (esse valor vai corresponder vICMSOp no XML (valor do ICMS como se nao tivesse diferimento), ao invés do vICMS)
            if record.icms_cst_code in ("00", "10", "20", "70", "51", "90", "900"):
                record.icms_value = record.icms_bc_value * record.icms_tax_percent / 100
            else:
                record.icms_value = False

    @api.constrains("icms_value")
    def _check_icms_value(self):
        for record in self:
            if (
                record.icms_cst_code
                in ("101", "102", "103", "201", "202", "203", "300", "400", "500")
                and record.icms_value
            ):
                raise ValidationError(
                    _(
                        f"O CSOSN {record.icms_cst_code} não admite informar o valor do ICMS para o item da nota fiscal: {record.product_description}."
                    )
                )
            elif (
                record.icms_cst_code in ("30", "40", "41", "50", "60")
                and record.icms_value
            ):
                raise ValidationError(
                    _(
                        f"O ICMS CST {record.icms_cst_code} não admite informar o valor do ICMS para o item da nota fiscal: {record.product_description}."
                    )
                )
            if record.icms_value and record.icms_value <= 0:
                raise ValidationError(
                    _(
                        f"O valor do ICMS é invalido para o item da nota fiscal: {record.product_description}."
                    )
                )

    # ICMS desonerado, apenas deve ser informado para os seguintes CSTs:
    # 20 - isenta ou nao tributada com cobrança de ICMS por ST
    # 30 - isenta
    # 40 - isenta
    # 41 - nao tributada
    # 50 - suspensao
    # 70 - com redução de base de calculo e cobrança de ICMS por ST
    # 90 - outros

    icms_deson_enabled = fields.Boolean(
        string="ICMS Desoneração Habilitado",
        compute="_compute_icms_deson_enabled",
        store=False,
    )

    @api.depends("icms_cst_code")
    def _compute_icms_deson_enabled(self):
        for record in self:
            record.icms_deson_enabled = record.icms_cst_code in (
                "20",
                "30",
                "40",
                "41",
                "50",
                "70",
                "90",
            )

    @api.onchange("icms_cst_id")
    def _onchange_icms_cst_id_clear_deson(self):
        for record in self:
            if record.icms_cst_id.code not in (
                "20",
                "30",
                "40",
                "41",
                "50",
                "70",
                "90",
            ):
                record.icms_deson_value = 0.0
                record.icms_deson_reason = False

    is_imunne_cst = fields.Boolean(
        string="É CST Imune",
        compute="_compute_is_imunne_cst",
        store=False,
    )

    @api.depends("icms_cst_id")
    def _compute_is_imunne_cst(self):
        for record in self:
            record.is_imunne_cst = record.icms_cst_id.code in ("40", "41", "50")

    icms_deson_value = fields.Float(
        string="Valor do ICMS Desoneração",
        digits=(13, 2),
        compute="_compute_icms_deson_value",
        readonly=False,
        store=True,
    )

    @api.depends("icms_cst_id")
    def _compute_icms_deson_value(self):
        for record in self:
            if record.icms_cst_id.code in ("40", "41", "50"):
                record.icms_deson_value = False
            else:
                record.icms_deson_value = 0.00

    icms_deson_reason = fields.Many2one(
        comodel_name="l10n_br_fiscal.icms.deson.reason",
        string="Motivo da Desoneração do ICMS",
        domain="[('cst_ids', 'in', icms_cst_id)]",
    )

    @api.constrains("icms_deson_reason", "icms_deson_value")
    def _check_icms_deson_required(self):
        for record in self:
            if (
                record.icms_deson_reason
                and not record.icms_deson_value
                and not record.is_imunne_cst
            ):
                raise ValidationError(
                    _(
                        "Produto: %s - O Valor do ICMS Desoneração é obrigatório quando o Motivo da Desoneração do ICMS está definido."
                    )
                    % record.product_description
                )
            elif record.icms_deson_value and record.icms_deson_value <= 0:
                raise ValidationError(
                    _(
                        f"O valor do ICMS Desoneração deve ser maior que zero para o item da nota fiscal: {record.product_description}."
                    )
                )

    # def _compute_icms_value(self):
    #     for record in self:
    #         record.icms_value = False
    # icms_group = self.env.ref("l10n_br_fiscal.tax_group_icms")
    # icms_st_group = self.env.ref("l10n_br_fiscal.tax_group_icmsst")
    # for record in self:
    #     if (
    #         record.icms_tax_id.tax_group_id == icms_group
    #         or record.icms_tax_id.tax_group_id == icms_st_group
    #     ) and self.icms_bc_modality == "3":
    #         record.icms_value = (
    #             record.icms_tax_id.percent_amount * record.icms_bc_value / 100
    #         )
    #     else:
    #         record.icms_value = False

    def _domain_icms_fcp_tax_id(self):
        return [
            ("tax_group_id", "=", self.env.ref("l10n_br_fiscal.tax_group_icmsfcp").id)
        ]

    can_have_icms_fcp = fields.Boolean(
        string="Pode ter FCP",
        compute="_compute_can_have_icms_fcp",
    )

    # somente tem FCP os seguintes CSTs:
    # 00 - Tributada integralmente
    # 10 - Tributada e com cobrança do ICMS por substituição tributária
    # 20 - Com redução de base de cálculo
    # 51 - tributação com diferimento
    # 70 - Com redução de BC e cobrança de ICMS por ST
    # 90 - outros
    @api.depends("icms_cst_code")
    def _compute_can_have_icms_fcp(self):
        for record in self:
            record.can_have_icms_fcp = record.icms_cst_code not in (
                "101",
                "102",
                "103",
                "201",
                "202",
                "203",
                "300",
                "400",
                "500",
                "900",
                "30",
                "40",
                "41",
                "50",
                "60",
            )

    icms_fcp_tax_id = fields.Many2one(
        comodel_name="l10n_br_fiscal.tax",
        string="FCP",
        domain=_domain_icms_fcp_tax_id,
    )

    @api.constrains("icms_fcp_tax_id", "can_have_icms_fcp")
    def _check_icms_fcp_tax_id(self):
        for record in self:
            if not record.can_have_icms_fcp and record.icms_fcp_tax_id:
                raise ValidationError(
                    _(
                        f"O FCP não deve ser informado para o item da nota fiscal: {record.product_description}."
                    )
                )

    icms_fcp_tax_percent = fields.Float(
        related="icms_fcp_tax_id.percent_amount",
        string="Aliquota do FCP",
        digits=(3, 4),
        store=True,
        readonly=True,
    )

    icms_fcp_bc_value = fields.Float(
        string="BC FCP`",
        digits=(13, 2),
        compute="_compute_icms_fcp_bc_value",
        store=True,
        readonly=False,
    )

    @api.depends("icms_bc_value", "icms_fcp_tax_id", "can_have_icms_fcp")
    def _compute_icms_fcp_bc_value(self):
        for record in self:
            if not record.can_have_icms_fcp:
                record.icms_fcp_bc_value = False
            elif record.icms_fcp_tax_id:
                record.icms_fcp_bc_value = record.icms_bc_value
            else:
                record.icms_fcp_bc_value = 0.00

    icms_fcp_value = fields.Float(
        string="Valor do FCP",
        digits=(13, 2),
        compute="_compute_icms_fcp_value",
        store=True,
        readonly=True,
    )

    @api.depends("can_have_icms_fcp", "icms_fcp_bc_value", "icms_fcp_tax_percent")
    def _compute_icms_fcp_value(self):
        for record in self:
            if record.can_have_icms_fcp:
                record.icms_fcp_value = (
                    record.icms_fcp_bc_value * record.icms_fcp_tax_percent / 100
                )
            else:
                record.icms_fcp_value = False

    allows_icms_sn_credit = fields.Boolean(
        string="Permite Crédito do ICMS SN",
        compute="_compute_allows_icms_sn_credit",
    )

    @api.depends("icms_cst_code")
    def _compute_allows_icms_sn_credit(self):
        for record in self:
            if record.icms_cst_code in ("101", "201", "900"):
                record.allows_icms_sn_credit = True
            else:
                record.allows_icms_sn_credit = False

    icms_sn_credit_percent = fields.Float(
        string="Aliquota de Crédito do ICMS SN",
        digits=(13, 2),
    )

    icms_sn_credit_value = fields.Float(
        string="Valor do Crédito do ICMS SN",
        digits=(13, 2),
    )

    @api.onchange(
        "allows_icms_sn_credit", "icms_sn_credit_percent", "icms_sn_credit_value"
    )
    def _onchange_icms_cst_code(self):
        for record in self:
            if not record.allows_icms_sn_credit:
                record.icms_sn_credit_percent = False
                record.icms_sn_credit_value = False

    @api.constrains("allows_icms_sn_credit", "icms_sn_credit_percent")
    def _check_icms_sn_credit(self):
        for record in self:
            if not record.allows_icms_sn_credit and record.icms_sn_credit_percent:
                raise ValidationError(
                    _(
                        f"O CSOSN {record.icms_cst_code} não admite informar a aliquota"
                        f" do crédito do ICMS SN. "
                        f"Validação referente ao item da nota fiscal: {record.product_description}."
                    )
                )

    @api.constrains("allows_icms_sn_credit", "icms_sn_credit_value")
    def _check_icms_sn_credit_value(self):
        for record in self:
            if not record.allows_icms_sn_credit and record.icms_sn_credit_value:
                raise ValidationError(
                    _(
                        f"O CSOSN {record.icms_cst_code} não admite informar o valor do crédito do ICMS SN. "
                        f"Validação referente ao item da nota fiscal: {record.product_description}."
                    )
                )

    @api.constrains("icms_sn_credit_percent", "icms_sn_credit_value")
    def _check_icms_sn_credit_required(self):
        for record in self:
            if record.icms_cst_code not in ("101", "201", "900"):
                continue

            icms_sn_credit_fields = [
                record.icms_sn_credit_percent,
                record.icms_sn_credit_value,
            ]

            if any(icms_sn_credit_fields) and not all(icms_sn_credit_fields):
                raise ValidationError(
                    _(
                        f"Para o CSOSN {record.icms_cst_code} se o grupo do ICMS SN for informado, é obrigatório "
                        f"informar a aliquota de crédito do ICMS SN ou o valor do crédito do ICMS SN. Validação referente ao item da nota "
                        f"fiscal: {record.product_description}."
                    )
                )

    # ===  icms ===
    # origem de marcadoria 0-8
    # CST
    # modalide da base de calculo
    # valor da base de calculo
    # percentual de reducao da base de calculo
    # percentual do diferimento pra caso de icms defirido
    # valor do icms diferido
    # aliquota do ICMS
    # valor ICMS
    # base de calcuo FCP
    # FCP aliquota
    # FCP valor

    # simples nacional
    # csosn
    # aliquota de credito
    # valor credito icms

    # CST 60 e CSOSN 500 - grupos opcionais nao implementados ICMS cobrado antiriorment por ST
    # valor da BC do icms st retido  - CTS 60 Tributação ICMS cobrado anteriormente por substituição tributária
    # aliquota suportada pelo consumidor final - CTS 60  Deve ser informada a alíquota do cálculo do ICMS-ST, já incluso o FCP caso incida sobre a mercadoria. Exemplo: alíquota da mercadoria na venda ao consumidor final = 18% e 2% de FCP. A alíquota a ser informada no campo pST deve ser 20%. (Atualizado NT2016.002)
    # valor do icms do subistituto - CTS 60 Tributação ICMS cobrado anteriormente por substituição tributária Valor do ICMS Próprio do Substituto cobrado em operação anterior (Criado na NT 2018.005. Atualizado na 2018.005 v1.20)
    # valor do icms st retido -  CST 60 Valor do ICMS ST cobrado anteriormente por ST (v2.0). O valor pode ser omitido quando a legislação não exigir a sua informação. (NT 2011/004)
    # BC FCP retido pro ST - CST 60 Informar o valor da Base de Cálculo do FCP retido anteriormente por ST
    # valor do FCP retido pro ST - CST 60 Informar o valor do FCP retido anteriormente por ST
    # aliquota do FCP retido pro ST - CST 60 Informar a alíquota do FCP retido anteriormente por ST

    # === ICMS ST ===

    is_icms_st_allowed = fields.Boolean(
        string="É CST com ICMS ST",
        compute="_compute_is_icms_st_allowed",
    )

    @api.depends("icms_cst_code")
    def _compute_is_icms_st_allowed(self):
        for record in self:
            record.is_icms_st_allowed = record.icms_cst_code in (
                "10",
                "30",
                "70",
                "90",
                "201",
                "202",
                "203",
                "900",
            )

    is_icms_st_required = fields.Boolean(
        string="É CST com ICMS ST obrigatório",
        compute="_compute_is_icmc_st_required",
    )

    @api.depends("icms_cst_code")
    def _compute_is_icmc_st_required(self):
        for record in self:
            record.is_icms_st_required = record.icms_cst_code in (
                "10",
                "30",
                "70",
                "201",
                "202",
                "203",
            )

    @api.onchange("is_icms_st_allowed", "icms_st_modality")
    def _onchange_is_icms_st_allowed(self):
        for record in self:
            if not record.is_icms_st_allowed:
                record.icms_st_modality = False

    icms_st_modality = fields.Selection(
        string="Modalidade da Base de Calculo do ICMS ST",
        selection=[
            ("0", "Preço tabelado ou máximo sugerido"),
            ("1", "Lista Negativa (valor)"),
            ("2", "Lista Positiva (valor)"),
            ("3", "Lista Neutra (valor)"),
            ("4", "Margem Valor Agregado (%)"),
            ("5", "Pauta (valor)"),
            ("6", "Valor da operação"),
        ],
        compute="_compute_icms_st_modality",
        readonly=False,
        store=True,
    )

    @api.depends("icms_cst_code")
    def _compute_icms_st_modality(self):
        for record in self:
            if not record.is_icms_st_allowed:
                record.icms_st_modality = False

    @api.constrains("is_icms_st_allowed", "icms_st_modality")
    def _check_icms_st_modality(self):
        for record in self:
            if not record.is_icms_st_allowed and record.icms_st_modality:
                raise ValidationError(
                    f"Produto: {record.product_description} - Modalidade da Base de Calculo do ICMS ST não pode ser informada para o CST {record.icms_cst_code}."
                )
            if record.is_icms_st_required:
                if not record.icms_st_modality:
                    raise ValidationError(
                        f"Produto: {record.product_description} - Modalidade da Base de Calculo do ICMS ST é obrigatório pro CST {record.icms_cst_code}."
                    )
                else:
                    if record.icms_st_modality not in (
                        "0",
                        "1",
                        "2",
                        "3",
                        "4",
                        "5",
                        "6",
                    ):
                        raise ValidationError(
                            f"Produto: {record.product_description} - Modalidade da Base de Calculo do ICMS ST é inválida para o CST {record.icms_cst_code}: {record.icms_st_modality}."
                        )

    is_icms_st_mva_modality = fields.Boolean(
        string="É modalidade de base de calculo do ICMS ST MVA",
        compute="_compute_is_icms_st_mva_modality",
    )

    @api.depends("icms_st_modality")
    def _compute_is_icms_st_mva_modality(self):
        for record in self:
            record.is_icms_st_mva_modality = record.icms_st_modality == "4"

    icms_st_mva_percent = fields.Float(
        string="MVA ICMS ST",
        digits=(3, 4),
        compute="_compute_icms_st_mva_percent",
        store=True,
        readonly=False,
    )

    @api.depends("icms_st_modality")
    def _compute_icms_st_mva_percent(self):
        for record in self:
            if not record.is_icms_st_allowed or record.icms_st_modality != "4":
                record.icms_st_mva_percent = False

    @api.constrains("icms_st_mva_percent")
    def _check_icms_st_mva_percent(self):
        for record in self:
            if record.icms_st_modality == "4" and record.icms_st_mva_percent <= 0:
                raise ValidationError(
                    f"Produto: {record.product_description} - MVA ICMS ST deve ser maior que 0 para a modalidade da Base de Calculo do ICMS ST Margem Valor Agregado (%) {record.icms_st_modality}."
                )
            elif record.icms_st_modality == "4" and not record.icms_st_mva_percent:
                raise ValidationError(
                    f"Produto: {record.product_description} - MVA ICMS ST é obrigatório para a modalidade da Base de Calculo do ICMS ST Margem Valor Agregado (%) {record.icms_st_modality}."
                )

    icms_st_reduction_percent = fields.Float(
        string="Percentual de Redução da Base de Calculo do ICMS ST",
        digits=(3, 4),
        compute="_compute_icms_st_reduction_percent",
        store=True,
        readonly=False,
    )

    @api.depends("icms_st_modality")
    def _compute_icms_st_reduction_percent(self):
        for record in self:
            if not record.is_icms_st_allowed or record.icms_st_modality != "4":
                record.icms_st_reduction_percent = False

    icms_st_bc_value = fields.Float(
        string="Valor da Base de Calculo do ICMS ST",
        digits=(13, 2),
        compute="_compute_icms_st_bc_value",
        store=True,
        readonly=False,
    )

    def _compute_icms_st_bc_value(self):
        for record in self:
            if not record.is_icms_st_allowed:
                record.icms_st_bc_value = False
            # deve ser inserido pelo próprio usuário
            elif record.icms_st_modality != "4":
                record.icms_st_bc_value = 0.00
            else:
                # se o emitente é simples nacional, o ipi nao é considerado na base de calculo do icms st
                ipi_value = record.ipi_value if not record.is_simples_nacional else 0
                base = (
                    record.total_value
                    + record.freight_value
                    + record.insurance_value
                    + record.other_expenses_value
                    - record.discount_value
                    + ipi_value
                )
                record.icms_st_bc_value = (
                    base
                    * (1 + record.icms_st_mva_percent / 100)
                    * (1 - record.icms_st_reduction_percent / 100)
                )

    @api.constrains("is_icms_st_allowed", "icms_st_bc_value")
    def _check_icms_st_bc_value(self):
        for record in self:
            if not record.is_icms_st_allowed and record.icms_st_bc_value:
                raise ValidationError(
                    f"Produto: {record.product_description} - Valor da Base de Calculo do ICMS ST não pode ser informado para o CST {record.icms_cst_code}."
                )
            elif record.is_icms_st_allowed and record.icms_st_bc_value <= 0:
                raise ValidationError(
                    f"Produto: {record.product_description} - Valor da Base de Calculo do ICMS ST deve ser maior que 0 para o CST {record.icms_cst_code}."
                )
            elif record.is_icms_st_required and not record.icms_st_bc_value:
                raise ValidationError(
                    f"Produto: {record.product_description} - Valor da Base de Calculo do ICMS ST é obrigatório para o CST {record.icms_cst_code}."
                )

    icms_st_tax_percent = fields.Float(
        string="Aliquota do ICMS ST",
        digits=(3, 4),
        compute="_compute_icms_st_tax_percent",
        store=True,
        readonly=False,
    )

    @api.depends("is_icms_st_allowed")
    def _compute_icms_st_tax_percent(self):
        for record in self:
            if not record.is_icms_st_allowed:
                record.icms_st_tax_percent = False

    @api.constrains("is_icms_st_allowed", "icms_st_tax_percent")
    def _check_icms_st_tax_percent(self):
        for record in self:
            if not record.is_icms_st_allowed and record.icms_st_tax_percent:
                raise ValidationError(
                    f"Produto: {record.product_description} - Aliquota do ICMS ST não pode ser informada para o CST {record.icms_cst_code}."
                )
            elif record.is_icms_st_allowed and record.icms_st_tax_percent <= 0:
                raise ValidationError(
                    f"Produto: {record.product_description} - Aliquota do ICMS ST deve ser maior que 0 para o CST {record.icms_cst_code}."
                )
            elif record.is_icms_st_required and not record.icms_st_bc_value:
                raise ValidationError(
                    f"Produto: {record.product_description} - Aliquota do ICMS ST é obrigatória para o CST {record.icms_cst_code}."
                )

    icms_st_value = fields.Float(
        string="Valor do ICMS ST",
        digits=(13, 2),
        compute="_compute_icms_st_value",
        store=True,
        readonly=True,
    )

    @api.depends(
        "is_icms_st_allowed",
        "icms_st_bc_value",
        "icms_st_tax_percent",
        "is_simples_nacional",
        "icms_value",
    )
    def _compute_icms_st_value(self):
        for record in self:
            if not record.is_icms_st_allowed:
                record.icms_st_value = False
            elif not record.is_simples_nacional:
                record.icms_st_value = (
                    record.icms_st_bc_value * record.icms_st_tax_percent / 100
                    - record.icms_st_reduction_value * record.icms_value
                )
            elif record.is_simples_nacional:
                # TODO: implementar o calculo do ICMS ST para simples nacional
                # O simples mesmo não destacando o ICMS da operação própria,
                #  o calcula pra descontar do mva*base icms st - icms da
                # operacao propria = ICMS-ST
                record.icms_st_value = 0.00

    @api.constrains("is_icms_st_allowed", "icms_st_value")
    def _check_icms_st_value(self):
        for record in self:
            if not record.is_icms_st_allowed and record.icms_st_value:
                raise ValidationError(
                    f"Produto: {record.product_description} - Valor do ICMS ST não pode ser informado para o CST {record.icms_cst_code}."
                )
            elif record.is_icms_st_allowed and record.icms_st_value <= 0:
                raise ValidationError(
                    f"Produto: {record.product_description} - Valor do ICMS ST deve ser maior que 0 para o CST {record.icms_cst_code}."
                )
            elif record.is_icms_st_required and not record.icms_st_value:
                raise ValidationError(
                    f"Produto: {record.product_description} - Valor do ICMS ST é obrigatório para o CST {record.icms_cst_code}."
                )

    def _domain_icms_st_fcp_tax_id(self):
        return [
            (
                "tax_group_id",
                "=",
                self.env.ref("l10n_br_fiscal.tax_group_icmsfcp_st").id,
            )
        ]

    icms_st_fcp_tax_id = fields.Many2one(
        comodel_name="l10n_br_fiscal.tax",
        string="FCP ST",
        domain=_domain_icms_st_fcp_tax_id,
    )

    @api.constrains("is_icms_st_allowed", "icms_st_fcp_tax_id")
    def _check_icms_st_fcp_tax_id(self):
        for record in self:
            if not record.is_icms_st_allowed and record.icms_st_fcp_tax_id:
                raise ValidationError(
                    f"Produto: {record.product_description} - FCP ST não pode ser informado para o CST {record.icms_cst_code}."
                )

    icms_st_fcp_tax_percent = fields.Float(
        related="icms_st_fcp_tax_id.percent_amount",
        string="Aliquota do FCP ST",
        digits=(13, 2),
        store=True,
        readonly=True,
    )

    @api.constrains("is_icms_st_allowed", "icms_st_fcp_tax_percent")
    def _check_icms_st_fcp_tax_percent(self):
        for record in self:
            if not record.is_icms_st_allowed and record.icms_st_fcp_tax_percent:
                raise ValidationError(
                    f"Produto: {record.product_description} - Aliquota do FCP ST não pode ser informada para o CST {record.icms_cst_code}."
                )

    icms_st_fcp_bc_value = fields.Float(
        string="Valor da Base de Calculo do FCP ST",
        digits=(13, 2),
        compute="_compute_icms_st_fcp_bc_value",
        store=True,
        readonly=True,
    )

    @api.depends("is_icms_st_allowed", "icms_st_bc_value", "icms_st_fcp_tax_id")
    def _compute_icms_st_fcp_bc_value(self):
        for record in self:
            if not record.is_icms_st_allowed:
                record.icms_st_fcp_bc_value = False
            elif record.icms_st_fcp_tax_id:
                record.icms_st_fcp_bc_value = record.icms_st_bc_value
            else:
                record.icms_st_fcp_bc_value = 0.00

    @api.constrains("is_icms_st_allowed", "icms_st_fcp_bc_value", "icms_st_fcp_tax_id")
    def _check_icms_st_fcp_bc_value(self):
        for record in self:
            if not record.is_icms_st_allowed and record.icms_st_fcp_bc_value:
                raise ValidationError(
                    f"Produto: {record.product_description} - Valor da Base de Calculo do FCP ST não pode ser informado para o CST {record.icms_cst_code}."
                )
            elif (
                record.is_icms_st_allowed
                and record.icms_st_fcp_tax_id
                and (
                    record.icms_st_fcp_bc_value == False
                    or record.icms_st_fcp_bc_value <= 0
                )
            ):
                raise ValidationError(
                    f"Produto: {record.product_description} - Valor da Base de Calculo do FCP ST é obrigatório para o CST {record.icms_cst_code}."
                )

    icms_st_fcp_value = fields.Float(
        string="Valor do FCP ST",
        digits=(13, 2),
        compute="_compute_icms_st_fcp_value",
        store=True,
        readonly=True,
    )

    @api.depends(
        "icms_st_fcp_tax_percent",
        "icms_st_fcp_bc_value",
        "is_icms_st_allowed",
        "icms_st_fcp_tax_id",
    )
    def _compute_icms_st_fcp_value(self):
        for record in self:
            if (
                record.is_icms_st_allowed
                and record.icms_st_fcp_tax_id
                and record.icms_st_fcp_bc_value
            ):
                record.icms_st_fcp_value = (
                    record.icms_st_fcp_bc_value * record.icms_st_fcp_tax_percent / 100
                )
            else:
                record.icms_st_fcp_value = False

    @api.constrains("is_icms_st_allowed", "icms_st_fcp_value", "icms_st_fcp_tax_id")
    def _check_icms_st_fcp_value(self):
        for record in self:
            if not record.is_icms_st_allowed and record.icms_st_fcp_value:
                raise ValidationError(
                    f"Produto: {record.product_description} - Valor do FCP ST não pode ser informado para o CST {record.icms_cst_code}."
                )
            elif (
                record.is_icms_st_allowed
                and record.icms_st_fcp_tax_id
                and (record.icms_st_fcp_bc_value or record.icms_st_fcp_value <= 0)
            ):
                raise ValidationError(
                    f"Produto: {record.product_description} - Valor do FCP ST é obrigatório para o CST {record.icms_cst_code}."
                )

    # icms_st modalidade
    # mva icms_st porcentagem
    # percentual_reducao_base_calculo_st
    # valor da base de calculo icms st
    # aliquota_ icms st
    # valor_icms_st
    # base de calculo fcp ST
    # percentual fcp st
    # valor fcp st

    # === ICMS ST Retido Anteriormente por Substituição Tributária ===
    # se para revenda, deve ser informado a base do ST, aliquota e valor. O mesmo vale para o FCP ST.

    icms_st_retention_base_value = fields.Float(
        string="Valor da Base de Calculo do ICMS ST Retido Anteriormente por Substituição Tributária",
        digits=(13, 2),
    )

    icms_st_retention_tax_percent = fields.Float(
        string="Alíquota suportada pelo Consumidor Final", digits=(3, 4)
    )

    icms_st_retention_value = fields.Float(
        string="Valor do ICMS ST Retido Anteriormente por Substituição Tributária",
        digits=(13, 2),
    )

    icms_do_substituto_value = fields.Float(
        string="Valor do ICMS Próprio do Substituto",
        digits=(13, 2),
    )

    icms_st_fcp_retention_base_value = fields.Float(
        string="Valor da Base de Calculo do FCP ST Retido Anteriormente por Substituição Tributária",
        digits=(13, 2),
    )

    icms_st_fcp_retention_tax_percent = fields.Float(
        string="Alíquota suportada pelo Consumidor Final", digits=(3, 4)
    )

    icms_st_fcp_retention_value = fields.Float(
        string="Valor do FCP ST Retido Anteriormente por Substituição Tributária",
        digits=(13, 2),
    )

    # ===  ipi ===

    product_has_ipi = fields.Boolean(
        string="Produto tem IPI",
        compute="_compute_product_has_ipi",
        readonly=True,
    )

    @api.depends("product_id")
    def _compute_product_has_ipi(self):
        for record in self:
            record.product_has_ipi = record.product_id.fiscal_type_id.code == "04"

    ipi_guideline_id = fields.Many2one(
        comodel_name="l10n_br_fiscal.ipi.guideline",
        string="Código de Enquadramento",
        compute="_compute_ipi_guideline_id",
        store=True,
        readonly=True,
    )

    @api.depends("is_simples_nacional", "product_id", "product_id.ipi_guideline_id")
    def _compute_ipi_guideline_id(self):
        for record in self:
            if record.is_simples_nacional:
                record.ipi_guideline_id = self.env.ref(
                    "l10n_br_fiscal.ipi_guideline_999"
                )
            elif record.product_id.ipi_guideline_id:
                record.ipi_guideline_id = record.product_id.ipi_guideline_id

    @api.constrains("ipi_guideline_id")
    def _check_ipi_guideline_id(self):
        for record in self:
            if not record.product_has_ipi and not record.ipi_guideline_id:
                raise ValidationError(_("O Código de Enquadramento é obrigatório."))

    ipi_guideline_code = fields.Char(
        string="Código de Enquadramento", size=3, related="ipi_guideline_id.code"
    )

    allowed_ipi_tax_ids = fields.Many2many(
        comodel_name="l10n_br_fiscal.tax",
        string="Allowed CSTs",
        compute="_compute_allowed_ipi_tax_ids",
    )

    # filtra os impostos de IPI associados ao CST de entrada ou saída do código de enquadramento
    @api.depends(
        "ipi_guideline_id",
        "ipi_guideline_id.ipi_cst_in",
        "ipi_guideline_id.ipi_cst_out",
        "operation_type",
    )
    def _compute_allowed_ipi_tax_ids(self):
        ipi_group = self.env.ref("l10n_br_fiscal.tax_group_ipi")
        for record in self:
            selected_cst = False
            if record.operation_type == "0":
                if record.ipi_guideline_id.ipi_cst_in:
                    record.allowed_ipi_tax_ids = self.env["l10n_br_fiscal.tax"].search(
                        [
                            ("tax_group_id", "=", ipi_group.id),
                            ("cst_in_id", "=", selected_cst.id),
                        ]
                    )
                else:
                    record.allowed_ipi_tax_ids = self.env["l10n_br_fiscal.tax"].search(
                        [("tax_group_id", "=", ipi_group.id)]
                    )
            elif record.operation_type == "1":
                if record.ipi_guideline_id.ipi_cst_out:
                    record.allowed_ipi_tax_ids = self.env["l10n_br_fiscal.tax"].search(
                        [
                            ("tax_group_id", "=", ipi_group.id),
                            ("cst_out_id", "=", record.ipi_guideline_id.ipi_cst_out.id),
                        ]
                    )
                else:
                    record.allowed_ipi_tax_ids = self.env["l10n_br_fiscal.tax"].search(
                        [("tax_group_id", "=", ipi_group.id)]
                    )
            else:
                record.allowed_ipi_tax_ids = False

    # empresa do simples utilizar ipi de saida 99 com valor zero quando for contruibinte do ipi - 99 outras saidas
    # simples NAO contribuinte do ipi e empresa no regime normal que nao tributa ipi (comercio) utilizar ipi de saida 53 - saida nao tributada
    # devolucao de mercadoria utilizar 53
    # industria utilizar os outros CST apropriados

    forced_ipi_tax_id = fields.Many2one(
        comodel_name="l10n_br_fiscal.tax",
        string="IPI",
        compute="_compute_forced_ipi_tax_id",
    )

    @api.depends(
        "is_simples_nacional",
        "issuer_contributes_to_ipi",
    )
    def _compute_forced_ipi_tax_id(self):
        for record in self:
            if record.is_simples_nacional:
                if record.issuer_contributes_to_ipi:
                    record.forced_ipi_tax_id = record.env.ref(
                        "l10n_br_fiscal.tax_ipi_outros"
                    ).id
                else:
                    record.forced_ipi_tax_id = record.env.ref(
                        "l10n_br_fiscal.tax_ipi_nt"
                    ).id
            else:
                record.forced_ipi_tax_id = False

    ipi_tax_id = fields.Many2one(
        comodel_name="l10n_br_fiscal.tax",
        string="IPI",
        compute="_compute_ipi_tax_id",
        domain="[('id', 'in', allowed_ipi_tax_ids)]",
        store=True,
    )

    @api.depends("forced_ipi_tax_id", "product_id", "product_id.ipi_tax_id")
    def _compute_ipi_tax_id(self):
        for record in self:
            if record.forced_ipi_tax_id:
                record.ipi_tax_id = record.forced_ipi_tax_id
            elif record.product_id.ipi_tax_id:
                record.ipi_tax_id = record.product_id.ipi_tax_id

    @api.constrains("ipi_tax_id")
    def _check_ipi_tax_id(self):
        for record in self:
            if record.product_has_ipi and not record.ipi_tax_id:
                raise ValidationError(_("O IPI é obrigatório."))

    is_ipi_qtt = fields.Boolean(
        string="IPI Tributado por Unidade",
        compute="_compute_is_ipi_qtt",
        readonly=True,
    )

    @api.depends("ipi_tax_id")
    def _compute_is_ipi_qtt(self):
        for record in self:
            record.is_ipi_qtt = record.ipi_tax_id == self.env.ref(
                "l10n_br_fiscal.tax_ipi_qtt"
            )

    # empresa do simples utilizar ipi de saida 99 com valor zero quando for contruibinte do ipi
    # simples NAO contribuinte do ipi e empresa no regime normal que nao tributa ipi (comercio) utilizar ipi de saida 53
    # TODO:devolucao de mercadoria utilizar 53
    # industria utilizar os outros CST apropriados
    ipi_cst_id = fields.Many2one(
        related="ipi_tax_id.cst_out_id",
        string="CST IPI",
        readonly=True,
        store=True,
    )

    @api.constrains("ipi_cst_id")
    def _check_ipi_cst_id(self):
        for record in self:
            if record.product_has_ipi and not record.ipi_cst_id:
                raise ValidationError(_("O CST IPI é obrigatório."))

    ipi_cst = fields.Char(
        related="ipi_cst_id.code", string="CST IPI", size=2, store=True, readonly=True
    )

    @api.constrains("ipi_cst")
    def _check_ipi_cst(self):
        for record in self:
            if record.product_has_ipi and not record.ipi_cst:
                raise ValidationError(_("O CST IPI é obrigatório."))

    is_ipi_with_percentage = fields.Boolean(
        string="É CST com Aliquota em Percentual",
        compute="_compute_is_ipi_with_percentage",
    )

    # 00 - entrade com recuperação de crédito
    # 50 - saida tributada
    # 49 - outras entradas
    # 99 - outras saídas
    @api.depends("ipi_cst_id")
    def _compute_is_ipi_with_percentage(self):
        for record in self:
            record.is_ipi_with_percentage = record.ipi_cst_id.code in (
                "00",
                "50",
                "49",
                "99",
            )

    is_relugar_ipi = fields.Boolean(
        string="É CST com Regulamento do IPI",
        compute="_compute_is_relugar_ipi",
    )

    @api.depends("ipi_cst_id")
    def _compute_is_relugar_ipi(self):
        for record in self:
            record.is_relugar_ipi = record.ipi_cst_id.code in ("00", "50")

    ipi_tax_percent = fields.Float(
        related="ipi_tax_id.percent_amount",
        string="Aliquota",
        digits=(3, 4),
        readonly=True,
        store=True,
    )

    @api.constrains("ipi_tax_percent")
    def _check_ipi_tax_percent(self):
        for record in self:
            if (
                record.is_relugar_ipi
                and not record.is_ipi_qtt
                and record.ipi_tax_percent <= 0
            ):
                raise ValidationError(
                    _(
                        "A Aliquota do IPI é obrigatória e deve ser maior que 0 para o CST {record.ipi_cst}."
                    )
                )

    ipi_bc_value = fields.Float(
        string="Valor da Base de Calculo do IPI",
        digits=(13, 2),
        compute="_compute_ipi_bc_value",
        readonly=True,
    )

    # Decisão do STF (Tema 84): Definiu que frete, seguro e descontos incondicionais não compõem a base de cálculo.
    @api.depends(
        "issuer_id.fiscal_framework",
        "is_ipi_qtt",
        "is_ipi_with_percentage",
        "total_value",
        "other_expenses_value",
        "discount_value",
        "freight_value",
        "insurance_value",
    )
    def _compute_ipi_bc_value(self):
        for record in self:
            if record._is_issuer_simples_nacional():
                record.ipi_bc_value = 0.00
            elif record.is_ipi_qtt:
                record.ipi_bc_value = False
            elif not record.is_ipi_with_percentage:
                record.ipi_bc_value = 0.00
            else:
                record.ipi_bc_value = (
                    record.total_value
                    + record.freight_value
                    + record.insurance_value
                    + record.other_expenses_value
                    - record.discount_value
                )

    @api.constrains("ipi_bc_value")
    def _check_ipi_bc_value(self):
        for record in self:
            if (
                record.is_relugar_ipi
                and not record.is_ipi_qtt
                and record.ipi_bc_value <= 0
            ):
                raise ValidationError(
                    _(
                        "O Valor da Base de Calculo do IPI é obrigatório e deve ser maior que 0 para o CST {record.ipi_cst}."
                    )
                )

    ipi_unit_value = fields.Float(
        string="Valor na Unidade Tributavel",
        digits=(13, 2),
        compute="_compute_ipi_unit_value",
        store=True,
        readonly=False,
    )

    @api.depends("is_ipi_qtt")
    def _compute_ipi_unit_value(self):
        for record in self:
            if not record.is_ipi_qtt:
                record.ipi_unit_value = False

    @api.constrains("ipi_unit_value")
    def _check_ipi_unit_value(self):
        for record in self:
            if record.is_ipi_qtt and not record.ipi_unit_value:
                raise ValidationError(_("O Valor na Unidade Tributável é obrigatório."))
            elif record.is_ipi_qtt and record.ipi_unit_value <= 0:
                raise ValidationError(
                    _("O Valor na Unidade Tributável deve ser maior que 0.")
                )

    ipi_unit_quantity = fields.Float(
        string="Quantidade na Unidade Tributavel",
        digits=(13, 4),
        compute="_compute_ipi_unit_quantity",
        store=True,
        readonly=False,
    )

    @api.depends("is_ipi_qtt")
    def _compute_ipi_unit_quantity(self):
        for record in self:
            if not record.is_ipi_qtt:
                record.ipi_unit_quantity = False

    @api.constrains("ipi_unit_quantity")
    def _check_ipi_unit_quantity(self):
        for record in self:
            if record.is_ipi_qtt and not record.ipi_unit_quantity:
                raise ValidationError(
                    _("A Quantidade na Unidade Tributável é obrigatória.")
                )
            elif record.is_ipi_qtt and record.ipi_unit_quantity <= 0:
                raise ValidationError(
                    _("A Quantidade na Unidade Tributável deve ser maior que 0.")
                )

    ipi_value = fields.Float(
        string="Valor do IPI",
        digits=(13, 2),
        readonly=True,
        compute="_compute_ipi_value",
        store=True,
    )

    @api.depends(
        "ipi_bc_value",
        "ipi_tax_percent",
        "is_ipi_qtt",
        "ipi_unit_value",
        "ipi_unit_quantity",
    )
    def _compute_ipi_value(self):
        for record in self:
            if record.is_ipi_qtt:
                record.ipi_value = record.ipi_unit_value * record.ipi_unit_quantity
            else:
                record.ipi_value = record.ipi_bc_value * record.ipi_tax_percent / 100

    # codigo de enquadramento
    # cst
    # aliquota
    # base de calculo
    # valor do ipi
    # quantidade na unidade tributavel
    # valor na unidade tributavel

    # === pis ===
    # empresa do simples
    # PIS
    # Campo CST “99” (Outras operações).
    # Tipo de Cálculo: Percentual.
    # Alíquota 0%.
    # Valor do COFINS: 0,00.

    allowed_pis_tax_ids = fields.Many2many(
        comodel_name="l10n_br_fiscal.tax",
        string="Allowed CSTs",
        compute="_compute_allowed_pis_tax_ids",
    )

    @api.depends(
        "is_simples_nacional", "issuer_id.regular_framework_type", "cofins_tax_id"
    )
    def _compute_allowed_pis_tax_ids(self):
        for record in self:
            if record.is_simples_nacional:
                record.allowed_pis_tax_ids = self.env.ref(
                    "l10n_br_fiscal.tax_pis_outras_operacoes"
                )
            elif record.cofins_tax_id:
                domain = [
                    (
                        "tax_group_id",
                        "=",
                        self.env.ref("l10n_br_fiscal.tax_group_pis").id,
                    ),
                    ("cst_out_id", "=", record.cofins_tax_id.cst_out_id.id),
                ]
                if record.issuer_id.regular_framework_type == "LP":
                    domain.append(
                        ("id", "!=", self.env.ref("l10n_br_fiscal.tax_pis_1_65").id)
                    )
                record.allowed_pis_tax_ids = self.env["l10n_br_fiscal.tax"].search(
                    domain
                )
            elif self.issuer_id.regular_framework_type == "LP":
                record.allowed_pis_tax_ids = self.env["l10n_br_fiscal.tax"].search(
                    [
                        (
                            "tax_group_id",
                            "=",
                            self.env.ref("l10n_br_fiscal.tax_group_pis").id,
                        ),
                        ("id", "!=", self.env.ref("l10n_br_fiscal.tax_pis_1_65").id),
                    ]
                )
            elif self.issuer_id.regular_framework_type == "LR":
                record.allowed_pis_tax_ids = self.env["l10n_br_fiscal.tax"].search(
                    [
                        (
                            "tax_group_id",
                            "=",
                            self.env.ref("l10n_br_fiscal.tax_group_pis").id,
                        )
                    ]
                )
            else:
                record.allowed_pis_tax_ids = False

    pis_tax_id = fields.Many2one(
        comodel_name="l10n_br_fiscal.tax",
        string="PIS",
        compute="_compute_pis_tax_id",
        store=True,
        domain="[('id', 'in', allowed_pis_tax_ids)]",
        readonly=False,
    )

    @api.depends("is_simples_nacional", "product_id", "product_id.pis_tax_id")
    def _compute_pis_tax_id(self):
        for record in self:
            if record.is_simples_nacional:
                record.pis_tax_id = record.env.ref(
                    "l10n_br_fiscal.tax_pis_outras_operacoes"
                ).id
            elif record.product_id.pis_tax_id:
                record.pis_tax_id = record.product_id.pis_tax_id
            else:
                record.pis_tax_id = False

    @api.constrains("pis_tax_id", "cofins_tax_id")
    def _check_pis_cst_and_cofins_cst(self):
        for record in self:
            if record.pis_tax_id.cst_out_id != record.cofins_tax_id.cst_out_id:
                raise ValidationError(
                    _(
                        "O PIS e COFINS devem ser informados simultaneamente e devem ter o mesmo CST."
                    )
                )

    pis_cst_id = fields.Many2one(
        related="pis_tax_id.cst_out_id",
        string="CST PIS",
        readonly=True,
        store=True,
    )

    pis_cst = fields.Char(
        related="pis_cst_id.code",
        string="CST PIS",
        size=2,
        store=True,
        readonly=True,
    )

    is_pis_qtt = fields.Boolean(
        string="PIS Tributado por Unidade",
        compute="_compute_is_pis_qtt",
        readonly=True,
    )

    @api.depends("pis_tax_id")
    def _compute_is_pis_qtt(self):
        for record in self:
            record.is_pis_qtt = record.pis_tax_id == self.env.ref(
                "l10n_br_fiscal.tax_pis_monofasico_qty"
            )

    is_pis_with_percentage = fields.Boolean(
        string="PIS com Aliquota em Percentual",
        compute="_compute_is_pis_with_percentage",
        readonly=True,
    )

    # 01 - Operação Tributável com Alíquota Básica
    # 02 - Operação Tributável com Alíquota Diferenciada
    # 03 - Operação Tributável com Alíquota por Unidade de Medida de Produto
    # 04 - Operação Tributável Monofásica - Revenda a Alíquota Zero
    # 05 - Operação Tributável por Substituição Tributária
    # 06 - Operação Tributável a Alíquota Zero
    # 07 - Operação Isenta da Contribuição
    # 08 - Operação sem Incidência da Contribuição
    # 09 - Operação com Suspensão da Contribuição
    # 49 - Outras Operações de Saída
    @api.depends("pis_cst_id")
    def _compute_is_pis_with_percentage(self):
        for record in self:
            record.is_pis_with_percentage = record.pis_cst_id.code in (
                "01",
                "02",
                "49",
            )

    pis_tax_percent = fields.Float(
        related="pis_tax_id.percent_amount",
        store=True,
        string="Aliquota do PIS",
        digits=(3, 4),
        readonly=True,
    )

    pis_bc_value = fields.Float(
        string="Valor da Base de Calculo do PIS",
        digits=(13, 2),
        readonly=True,
        store=True,
        compute="_compute_pis_bc_value",
    )

    def compute_pis_cofins_bc_value(self):
        for record in self:
            if record.is_simples_nacional:
                return 0.00
            else:
                return (
                    record.total_value
                    + record.freight_value
                    + record.insurance_value
                    + record.other_expenses_value
                    - record.discount_value
                    - (record.icms_value or 0.00)
                )

    @api.depends(
        "is_simples_nacional",
        "total_value",
        "freight_value",
        "insurance_value",
        "other_expenses_value",
        "discount_value",
        "icms_value",
        "is_pis_qtt",
        "is_pis_with_percentage",
    )
    def _compute_pis_bc_value(self):
        for record in self:
            if record.is_simples_nacional:
                record.pis_bc_value = 0.00
            elif record.is_pis_qtt:
                record.pis_bc_value = False
            elif not record.is_pis_with_percentage:
                record.pis_bc_value = False
            else:
                record.pis_bc_value = self.compute_pis_cofins_bc_value()

    @api.constrains("pis_bc_value", "is_pis_qtt", "is_pis_with_percentage")
    def _check_pis_bc_value(self):
        for record in self:
            if record.is_pis_qtt and record.pis_bc_value:
                raise ValidationError(
                    _(
                        "O Valor da Base de Calculo do PIS não pode ser informado para o CST {record.pis_cst}."
                    )
                )
            elif record.is_pis_with_percentage and not record.pis_bc_value:
                raise ValidationError(
                    _(
                        "O Valor da Base de Calculo do PIS é obrigatório para o CST {record.pis_cst}."
                    )
                )
            elif record.is_pis_with_percentage and record.pis_bc_value <= 0:
                raise ValidationError(
                    _(
                        "O Valor da Base de Calculo do PIS deve ser maior que 0 para o CST {record.pis_cst}."
                    )
                )

    pis_bc_quantity = fields.Float(
        string="Quantidade (Tributado por quantidade)",
        digits=(12, 4),
        compute="_compute_pis_bc_quantity",
        store=True,
        readonly=False,
    )

    @api.depends("is_pis_qtt")
    def _compute_pis_bc_quantity(self):
        for record in self:
            if not record.is_pis_qtt:
                record.pis_bc_quantity = False

    @api.constrains("is_pis_qtt", "pis_bc_quantity")
    def _check_pis_bc_quantity(self):
        for record in self:
            if record.is_pis_qtt and not record.pis_bc_quantity:
                raise ValidationError(
                    _("A Quantidade (Tributado por quantidade) é obrigatória.")
                )
            elif record.is_pis_qtt and record.pis_bc_quantity <= 0:
                raise ValidationError(
                    _("A Quantidade (Tributado por quantidade) deve ser maior que 0.")
                )

    pis_tax_quantity = fields.Float(
        string="Aliquota em reais (Tributado por quantidade)",
        digits=(11, 4),
        compute="_compute_pis_tax_quantity",
        store=True,
        readonly=False,
    )

    @api.depends("is_pis_qtt")
    def _compute_pis_tax_quantity(self):
        for record in self:
            if not record.is_pis_qtt:
                record.pis_tax_quantity = False

    @api.constrains("is_pis_qtt", "pis_tax_quantity")
    def _check_pis_tax_quantity(self):
        for record in self:
            if record.is_pis_qtt and not record.pis_tax_quantity:
                raise ValidationError(
                    _("A Aliquota em reais (Tributado por quantidade) é obrigatória.")
                )
            elif record.is_pis_qtt and record.pis_tax_quantity <= 0:
                raise ValidationError(
                    _(
                        "A Aliquota em reais (Tributado por quantidade) deve ser maior que 0."
                    )
                )

    pis_value = fields.Float(
        string="Valor do PIS",
        digits=(13, 2),
        readonly=True,
        store=True,
        compute="_compute_pis_value",
    )

    @api.depends(
        "pis_bc_value",
        "pis_tax_percent",
        "is_pis_qtt",
        "pis_bc_quantity",
        "pis_tax_quantity",
    )
    def _compute_pis_value(self):
        for record in self:
            if record.is_pis_qtt:
                record.pis_value = record.pis_bc_quantity * record.pis_tax_quantity
            else:
                record.pis_value = record.pis_bc_value * record.pis_tax_percent / 100

    # cst
    # base de calculo
    # aliquota em percentual
    # quantidade vendida
    # aliquota em valor
    # valor

    # ===  pis st ===

    allowed_pis_st_tax_ids = fields.Many2many(
        comodel_name="l10n_br_fiscal.tax",
        string="Allowed CSTs",
        compute="_compute_allowed_pis_st_tax_ids",
    )

    @api.depends("is_simples_nacional", "cofins_st_tax_id")
    def _compute_allowed_pis_st_tax_ids(self):
        for record in self:
            if record.is_simples_nacional:
                record.allowed_pis_st_tax_ids = False
            elif record.cofins_st_tax_id:
                record.allowed_pis_st_tax_ids = self.env["l10n_br_fiscal.tax"].search(
                    [
                        (
                            "tax_group_id",
                            "=",
                            self.env.ref("l10n_br_fiscal.tax_group_pisst").id,
                        ),
                        ("cst_out_id", "=", record.cofins_st_tax_id.cst_out_id.id),
                    ]
                )
            else:
                record.allowed_pis_st_tax_ids = self.env["l10n_br_fiscal.tax"].search(
                    [
                        (
                            "tax_group_id",
                            "=",
                            self.env.ref("l10n_br_fiscal.tax_group_pisst").id,
                        )
                    ]
                )

    pis_st_tax_id = fields.Many2one(
        comodel_name="l10n_br_fiscal.tax",
        string="PIS ST",
        compute="_compute_pis_st_tax_id",
        store=True,
        domain="[('id', 'in', allowed_pis_st_tax_ids)]",
        readonly=False,
    )

    @api.depends("is_simples_nacional")
    def _compute_pis_st_tax_id(self):
        for record in self:
            if record.is_simples_nacional:
                record.pis_st_tax_id = False

    pis_st_cst_id = fields.Many2one(
        related="pis_st_tax_id.cst_out_id",
        string="CST PIS ST",
        readonly=True,
        store=True,
    )

    pis_st_cst = fields.Char(
        related="pis_st_cst_id.code",
        string="CST PIS ST",
        size=2,
        store=True,
        readonly=True,
    )

    is_pis_st_qtt = fields.Boolean(
        string="PIS ST Tributado por Unidade",
        compute="_compute_is_pis_st_qtt",
        readonly=True,
    )

    @api.depends("pis_st_tax_id")
    def _compute_is_pis_st_qtt(self):
        for record in self:
            record.is_pis_st_qtt = record.pis_st_tax_id == self.env.ref(
                "l10n_br_fiscal.tax_pis_st_qty"
            )

    pis_st_tax_percent = fields.Float(
        related="pis_st_tax_id.percent_amount",
        store=True,
        string="Aliquota do PIS ST",
        digits=(3, 4),
        readonly=True,
    )

    pis_st_bc_value = fields.Float(
        string="Valor da Base de Calculo do PIS ST",
        digits=(13, 2),
        readonly=True,
        store=True,
        compute="_compute_pis_st_bc_value",
    )

    def compute_pis_cofins_st_bc_value(self):
        for record in self:
            if record.is_simples_nacional:
                return 0.00
            elif record.is_pis_st_qtt:
                return False
            else:
                return (
                    record.total_value
                    + record.freight_value
                    + record.insurance_value
                    + record.other_expenses_value
                    - record.discount_value
                    - (record.icms_value or 0.00)
                )

    @api.depends(
        "is_simples_nacional",
        "total_value",
        "freight_value",
        "insurance_value",
        "other_expenses_value",
        "discount_value",
        "icms_value",
        "is_pis_st_qtt",
        "pis_st_tax_id",
    )
    def _compute_pis_st_bc_value(self):
        for record in self:
            if record.is_simples_nacional:
                record.pis_st_bc_value = 0.00
            elif not record.pis_st_tax_id:
                record.pis_st_bc_value = False
            elif record.is_pis_st_qtt:
                record.pis_st_bc_value = False
            else:
                record.pis_st_bc_value = self.compute_pis_cofins_st_bc_value()

    @api.constrains("pis_st_bc_value", "is_pis_st_qtt", "pis_st_tax_id")
    def _check_pis_st_bc_value(self):
        for record in self:
            if record.is_pis_st_qtt and record.pis_st_bc_value:
                raise ValidationError(
                    _(
                        f"O Valor da Base de Calculo do PIS ST não pode ser informado para o CST {record.pis_st_cst_id.code}."
                    )
                )
            elif (
                record.pis_st_tax_id
                and not record.is_pis_st_qtt
                and (not record.pis_st_bc_value or record.pis_st_bc_value <= 0)
            ):
                raise ValidationError(
                    _(
                        f"O Valor da Base de Calculo do PIS ST é obrigatório para o CST {record.pis_st_cst_id.code}."
                    )
                )

    pis_st_bc_quantity = fields.Float(
        string="Quantidade (Tributado por quantidade)",
        digits=(12, 4),
        compute="_compute_pis_st_bc_quantity",
        store=True,
        readonly=False,
    )

    @api.depends("is_pis_st_qtt")
    def _compute_pis_st_bc_quantity(self):
        for record in self:
            if not record.is_pis_st_qtt:
                record.pis_st_bc_quantity = False

    @api.constrains("pis_st_bc_quantity", "is_pis_st_qtt")
    def _check_pis_st_bc_quantity(self):
        for record in self:
            if record.is_pis_st_qtt and not record.pis_st_bc_quantity:
                raise ValidationError(
                    _("A Quantidade (Tributado por quantidade) é obrigatória.")
                )
            elif record.is_pis_st_qtt and record.pis_st_bc_quantity <= 0:
                raise ValidationError(
                    _("A Quantidade (Tributado por quantidade) deve ser maior que 0.")
                )

    pis_st_tax_quantity = fields.Float(
        string="Aliquota em reais (Tributado por quantidade)",
        digits=(11, 4),
        compute="_compute_pis_st_tax_quantity",
        store=True,
        readonly=False,
    )

    @api.depends("is_pis_st_qtt")
    def _compute_pis_st_tax_quantity(self):
        for record in self:
            if not record.is_pis_st_qtt:
                record.pis_st_tax_quantity = False

    @api.constrains("pis_st_tax_quantity", "is_pis_st_qtt")
    def _check_pis_st_tax_quantity(self):
        for record in self:
            if record.is_pis_st_qtt and not record.pis_st_tax_quantity:
                raise ValidationError(
                    _("A Aliquota em reais (Tributado por quantidade) é obrigatória.")
                )
            elif record.is_pis_st_qtt and record.pis_st_tax_quantity <= 0:
                raise ValidationError(
                    _(
                        "A Aliquota em reais (Tributado por quantidade) deve ser maior que 0."
                    )
                )

    pis_st_value = fields.Float(
        string="Valor do PIS ST",
        digits=(13, 2),
        readonly=True,
        store=True,
        compute="_compute_pis_st_value",
    )

    @api.depends(
        "pis_st_bc_value",
        "pis_st_tax_percent",
        "is_pis_st_qtt",
        "pis_st_bc_quantity",
        "pis_st_tax_quantity",
    )
    def _compute_pis_st_value(self):
        for record in self:
            if record.is_pis_st_qtt:
                record.pis_st_value = (
                    record.pis_st_bc_quantity * record.pis_st_tax_quantity
                )
            else:
                record.pis_st_value = (
                    record.pis_st_bc_value * record.pis_st_tax_percent / 100
                )

    # cst
    # base de calculo
    # aliquota em percentual
    # quantidade vendida
    # aliquota em valor
    # valor do pis st

    # ===  cofins ===

    allowed_cofins_tax_ids = fields.Many2many(
        comodel_name="l10n_br_fiscal.tax",
        string="Allowed CSTs",
        compute="_compute_allowed_cofins_tax_ids",
    )

    @api.depends(
        "is_simples_nacional", "issuer_id.regular_framework_type", "pis_tax_id"
    )
    def _compute_allowed_cofins_tax_ids(self):
        for record in self:
            if record.is_simples_nacional:
                record.allowed_cofins_tax_ids = self.env.ref(
                    "l10n_br_fiscal.tax_cofins_outras_operacoes"
                )
            elif record.pis_tax_id:

                domain = [
                    (
                        "tax_group_id",
                        "=",
                        self.env.ref("l10n_br_fiscal.tax_group_cofins").id,
                    ),
                    ("cst_out_id", "=", record.pis_tax_id.cst_out_id.id),
                ]

                if record.issuer_id.regular_framework_type == "LP":
                    domain.append(
                        ("id", "!=", self.env.ref("l10n_br_fiscal.tax_cofins_7_6").id)
                    )

                record.allowed_cofins_tax_ids = self.env["l10n_br_fiscal.tax"].search(
                    domain
                )
            elif record.issuer_id.regular_framework_type == "LP":
                record.allowed_cofins_tax_ids = self.env["l10n_br_fiscal.tax"].search(
                    [
                        (
                            "tax_group_id",
                            "=",
                            self.env.ref("l10n_br_fiscal.tax_group_cofins").id,
                        ),
                        (
                            "id",
                            "!=",
                            self.env.ref("l10n_br_fiscal.tax_cofins_7_6").id,
                        ),
                    ]
                )
            elif record.issuer_id.regular_framework_type == "LR":
                record.allowed_cofins_tax_ids = self.env["l10n_br_fiscal.tax"].search(
                    [
                        (
                            "tax_group_id",
                            "=",
                            self.env.ref("l10n_br_fiscal.tax_group_cofins").id,
                        )
                    ]
                )
            else:
                record.allowed_cofins_tax_ids = False

    cofins_tax_id = fields.Many2one(
        comodel_name="l10n_br_fiscal.tax",
        string="COFINS",
        compute="_compute_cofins_tax_id",
        store=True,
        domain="[('id', 'in', allowed_cofins_tax_ids)]",
        readonly=False,
    )

    @api.depends("is_simples_nacional", "product_id", "product_id.cofins_tax_id")
    def _compute_cofins_tax_id(self):
        for record in self:
            if record.is_simples_nacional:
                record.cofins_tax_id = record.env.ref(
                    "l10n_br_fiscal.tax_cofins_outras_operacoes"
                ).id
            elif record.product_id.cofins_tax_id:
                record.cofins_tax_id = record.product_id.cofins_tax_id
            else:
                record.cofins_tax_id = False

    cofins_cst_id = fields.Many2one(
        related="cofins_tax_id.cst_out_id",
        string="CST COFINS",
        readonly=True,
        store=True,
    )

    cofins_cst = fields.Char(
        related="cofins_cst_id.code",
        string="CST COFINS",
        size=2,
        store=True,
        readonly=True,
    )

    is_cofins_qtt = fields.Boolean(
        string="COFINS Tributado por Unidade",
        compute="_compute_is_cofins_qtt",
        readonly=True,
    )

    @api.depends("cofins_tax_id")
    def _compute_is_cofins_qtt(self):
        for record in self:
            record.is_cofins_qtt = record.cofins_tax_id == self.env.ref(
                "l10n_br_fiscal.tax_cofins_value_monofasico_qty"
            )

    is_cofins_with_percentage = fields.Boolean(
        string="COFINS com Aliquota em Percentual",
        compute="_compute_is_cofins_with_percentage",
        readonly=True,
    )

    # 01 - Operação Tributável com Alíquota Básica
    # 02 - Operação Tributável com Alíquota Diferenciada
    # 03 - Operação Tributável com Alíquota por Unidade de Medida de Produto
    # 04 - Operação Tributável Monofásica - Revenda a Alíquota Zero
    # 05 - Operação Tributável por Substituição Tributária
    # 06 - Operação Tributável a Alíquota Zero
    # 07 - Operação Isenta da Contribuição
    # 08 - Operação sem Incidência da Contribuição
    # 09 - Operação com Suspensão da Contribuição
    # 49 - Outras Operações de Saída
    @api.depends("cofins_cst_id")
    def _compute_is_cofins_with_percentage(self):
        for record in self:
            record.is_cofins_with_percentage = record.cofins_cst_id.code in (
                "01",
                "02",
                "49",
            )

    cofins_tax_percent = fields.Float(
        related="cofins_tax_id.percent_amount",
        store=True,
        string="Aliquota do COFINS",
        digits=(3, 4),
        readonly=True,
    )

    cofins_bc_value = fields.Float(
        string="Valor da Base de Calculo do COFINS",
        digits=(13, 2),
        readonly=True,
        store=True,
        compute="_compute_cofins_bc_value",
    )

    @api.depends(
        "is_simples_nacional",
        "is_cofins_qtt",
        "is_cofins_with_percentage",
        "total_value",
        "freight_value",
        "insurance_value",
        "other_expenses_value",
        "discount_value",
        "icms_value",
    )
    def _compute_cofins_bc_value(self):
        for record in self:
            if record.is_simples_nacional:
                record.cofins_bc_value = 0.00
            elif record.is_cofins_qtt:
                record.cofins_bc_value = False
            elif not record.is_cofins_with_percentage:
                record.cofins_bc_value = False
            else:
                record.cofins_bc_value = self.compute_pis_cofins_bc_value()

    @api.constrains("cofins_bc_value", "is_cofins_qtt", "is_cofins_with_percentage")
    def _check_cofins_bc_value(self):
        for record in self:
            if record.is_cofins_qtt and record.cofins_bc_value:
                raise ValidationError(
                    _(
                        "O Valor da Base de Calculo do COFINS não pode ser informado para o CST {record.cofins_cst}."
                    )
                )
            elif record.is_cofins_with_percentage and not record.cofins_bc_value:
                raise ValidationError(
                    _(
                        "O Valor da Base de Calculo do COFINS é obrigatório para o CST {record.cofins_cst}."
                    )
                )
            elif record.is_cofins_with_percentage and record.cofins_bc_value <= 0:
                raise ValidationError(
                    _(
                        "O Valor da Base de Calculo do COFINS deve ser maior que 0 para o CST {record.cofins_cst}."
                    )
                )

    cofins_bc_quantity = fields.Float(
        string="Quantidade (Tributado por quantidade)",
        digits=(12, 4),
        compute="_compute_cofins_bc_quantity",
        store=True,
        readonly=False,
    )

    @api.depends("is_cofins_qtt")
    def _compute_cofins_bc_quantity(self):
        for record in self:
            if not record.is_cofins_qtt:
                record.cofins_bc_quantity = False

    @api.constrains("cofins_bc_quantity", "is_cofins_qtt")
    def _check_cofins_bc_quantity(self):
        for record in self:
            if record.is_cofins_qtt and not record.cofins_bc_quantity:
                raise ValidationError(
                    _("A Quantidade (Tributado por quantidade) é obrigatória.")
                )
            elif record.is_cofins_qtt and record.cofins_bc_quantity <= 0:
                raise ValidationError(
                    _("A Quantidade (Tributado por quantidade) deve ser maior que 0.")
                )

    cofins_tax_quantity = fields.Float(
        string="Aliquota em reais (Tributado por quantidade)",
        digits=(11, 4),
        compute="_compute_cofins_tax_quantity",
        store=True,
        readonly=False,
    )

    @api.depends("is_cofins_qtt")
    def _compute_cofins_tax_quantity(self):
        for record in self:
            if not record.is_cofins_qtt:
                record.cofins_tax_quantity = False

    @api.constrains("cofins_tax_quantity", "is_cofins_qtt")
    def _check_cofins_tax_quantity(self):
        for record in self:
            if record.is_cofins_qtt and not record.cofins_tax_quantity:
                raise ValidationError(
                    _("A Aliquota em reais (Tributado por quantidade) é obrigatória.")
                )
            elif record.is_cofins_qtt and record.cofins_tax_quantity <= 0:
                raise ValidationError(
                    _(
                        "A Aliquota em reais (Tributado por quantidade) deve ser maior que 0."
                    )
                )

    cofins_value = fields.Float(
        string="Valor do COFINS",
        digits=(13, 2),
        readonly=True,
        store=True,
        compute="_compute_cofins_value",
    )

    @api.depends(
        "cofins_bc_value",
        "cofins_tax_percent",
        "is_cofins_qtt",
        "cofins_bc_quantity",
        "cofins_tax_quantity",
    )
    def _compute_cofins_value(self):
        for record in self:
            if record.is_cofins_qtt:
                record.cofins_value = (
                    record.cofins_bc_quantity * record.cofins_tax_quantity
                )
            else:
                record.cofins_value = (
                    record.cofins_bc_value * record.cofins_tax_percent / 100
                )

    # cst
    # base de calculo
    # aliquota em percentual
    # quantidade vendida
    # aliquota em valor

    # ===  cofins st ===

    allowed_cofins_st_tax_ids = fields.Many2many(
        comodel_name="l10n_br_fiscal.tax",
        string="Allowed CSTs",
        compute="_compute_allowed_cofins_st_tax_ids",
    )

    @api.depends("is_simples_nacional", "pis_st_tax_id")
    def _compute_allowed_cofins_st_tax_ids(self):
        for record in self:
            if record.is_simples_nacional:
                record.allowed_cofins_st_tax_ids = False
            elif record.pis_st_tax_id:
                record.allowed_cofins_st_tax_ids = self.env[
                    "l10n_br_fiscal.tax"
                ].search(
                    [
                        (
                            "tax_group_id",
                            "=",
                            self.env.ref("l10n_br_fiscal.tax_group_cofinsst").id,
                        ),
                        ("cst_out_id", "=", record.pis_st_tax_id.cst_out_id.id),
                    ]
                )
            else:
                record.allowed_cofins_st_tax_ids = self.env[
                    "l10n_br_fiscal.tax"
                ].search(
                    [
                        (
                            "tax_group_id",
                            "=",
                            self.env.ref("l10n_br_fiscal.tax_group_cofinsst").id,
                        )
                    ]
                )

    cofins_st_tax_id = fields.Many2one(
        comodel_name="l10n_br_fiscal.tax",
        string="COFINS ST",
        compute="_compute_cofins_st_tax_id",
        store=True,
        domain="[('id', 'in', allowed_cofins_st_tax_ids)]",
        readonly=False,
    )

    @api.depends("is_simples_nacional")
    def _compute_cofins_st_tax_id(self):
        for record in self:
            if record.is_simples_nacional:
                record.cofins_st_tax_id = False

    cofins_st_cst_id = fields.Many2one(
        related="cofins_st_tax_id.cst_out_id",
        string="CST COFINS ST",
        readonly=True,
        store=True,
    )

    cofins_st_cst = fields.Char(
        related="cofins_st_cst_id.code",
        string="CST COFINS ST",
        size=2,
        store=True,
        readonly=True,
    )

    is_cofins_st_qtt = fields.Boolean(
        string="COFINS ST Tributado por Unidade",
        compute="_compute_is_cofins_st_qtt",
        readonly=True,
    )

    @api.depends("cofins_st_tax_id")
    def _compute_is_cofins_st_qtt(self):
        for record in self:
            record.is_cofins_st_qtt = record.cofins_st_tax_id == self.env.ref(
                "l10n_br_fiscal.tax_cofins_st_qty"
            )

    cofins_st_tax_percent = fields.Float(
        related="cofins_st_tax_id.percent_amount",
        store=True,
        string="Aliquota do COFINS ST",
        digits=(3, 4),
        readonly=True,
    )

    cofins_st_bc_value = fields.Float(
        string="Valor da Base de Calculo do COFINS ST",
        digits=(13, 2),
        readonly=True,
        store=True,
        compute="_compute_cofins_st_bc_value",
    )

    @api.depends(
        "is_simples_nacional",
        "cofins_st_tax_id",
        "is_cofins_st_qtt",
        "total_value",
        "freight_value",
        "insurance_value",
        "other_expenses_value",
        "discount_value",
        "icms_value",
    )
    def _compute_cofins_st_bc_value(self):
        for record in self:
            if record.is_simples_nacional:
                record.cofins_st_bc_value = 0.00
            elif not record.cofins_st_tax_id:
                record.cofins_st_bc_value = False
            elif record.is_cofins_st_qtt:
                record.cofins_st_bc_value = False
            else:
                record.cofins_st_bc_value = self.compute_pis_cofins_st_bc_value()

    @api.constrains(
        "cofins_st_bc_value",
        "is_cofins_st_qtt",
        "cofins_st_tax_id",
    )
    def _check_cofins_st_bc_value(self):
        for record in self:
            if record.is_cofins_st_qtt and record.cofins_st_bc_value:
                raise ValidationError(
                    _(
                        "O Valor da Base de Calculo do COFINS ST não pode ser informado para o CST {record.cofins_st_cst}."
                    )
                )
            elif (
                record.cofins_st_tax_id
                and not record.is_cofins_st_qtt
                and (not record.cofins_st_bc_value or record.cofins_st_bc_value <= 0)
            ):
                raise ValidationError(
                    _(
                        "O Valor da Base de Calculo do COFINS ST é obrigatório para o CST {record.cofins_st_cst}."
                    )
                )

    cofins_st_bc_quantity = fields.Float(
        string="Quantidade (Tributado por quantidade)",
        digits=(12, 4),
        compute="_compute_cofins_st_bc_quantity",
        store=True,
        readonly=False,
    )

    @api.depends("is_cofins_st_qtt")
    def _compute_cofins_st_bc_quantity(self):
        for record in self:
            if not record.is_cofins_st_qtt:
                record.cofins_st_bc_quantity = False

    @api.constrains("cofins_st_bc_quantity", "is_cofins_st_qtt")
    def _check_cofins_st_bc_quantity(self):
        for record in self:
            if record.is_cofins_st_qtt and not record.cofins_st_bc_quantity:
                raise ValidationError(
                    _("A Quantidade (Tributado por quantidade) é obrigatória.")
                )
            elif record.is_cofins_st_qtt and record.cofins_st_bc_quantity <= 0:
                raise ValidationError(
                    _("A Quantidade (Tributado por quantidade) deve ser maior que 0.")
                )

    cofins_st_tax_quantity = fields.Float(
        string="Aliquota em reais (Tributado por quantidade)",
        digits=(11, 4),
        compute="_compute_cofins_st_tax_quantity",
        store=True,
        readonly=False,
    )

    @api.depends("is_cofins_st_qtt")
    def _compute_cofins_st_tax_quantity(self):
        for record in self:
            if not record.is_cofins_st_qtt:
                record.cofins_st_tax_quantity = False

    @api.constrains("cofins_st_tax_quantity", "is_cofins_st_qtt")
    def _check_cofins_st_tax_quantity(self):
        for record in self:
            if record.is_cofins_st_qtt and not record.cofins_st_tax_quantity:
                raise ValidationError(
                    _("A Aliquota em reais (Tributado por quantidade) é obrigatória.")
                )
            elif record.is_cofins_st_qtt and record.cofins_st_tax_quantity <= 0:
                raise ValidationError(
                    _(
                        "A Aliquota em reais (Tributado por quantidade) deve ser maior que 0."
                    )
                )

    cofins_st_value = fields.Float(
        string="Valor do COFINS ST",
        digits=(13, 2),
        readonly=True,
        store=True,
        compute="_compute_cofins_st_value",
    )

    @api.depends(
        "cofins_st_bc_value",
        "cofins_st_tax_percent",
        "is_cofins_st_qtt",
        "cofins_st_bc_quantity",
        "cofins_st_tax_quantity",
    )
    def _compute_cofins_st_value(self):
        for record in self:
            if record.is_cofins_st_qtt:
                record.cofins_st_value = (
                    record.cofins_st_bc_quantity * record.cofins_st_tax_quantity
                )
            else:
                record.cofins_st_value = (
                    record.cofins_st_bc_value * record.cofins_st_tax_percent / 100
                )

    # cst
    # base de calculo
    # aliquota em percentual
    # quantidade vendida
    # aliquota em valor
    # valor do cofins st

    # @api.constrains('product_value', 'commercial_unit_value', 'commercial_quantity')
    # def _check_product_value_calculation(self):
    #     # Valida que o valor total do produto (vProd) é igual ao valor unitário comercial (vUnCom) multiplicado pela quantidade comercial (qCom).
    #     # Para NF-e Normal (finNFe=1): vProd difere de vUnCom * qCom (*4).
    #     for record in self:
    #         # Tolerância de 0.01 para arredondamento, conforme MOC nota (*4) [223, 261]
    #         calculated_value = round(record.commercial_unit_value * record.commercial_quantity, 2)
    #         if abs(record.product_value - calculated_value) > 0.01:
    #             raise ValidationError(_("O valor total do produto (vProd) do item %s difere do cálculo (Valor Unitário Comercial * Quantidade Comercial)." % record.sequence))

    # === Grupo P Imposto de Importação ===

    is_ii_allowed = fields.Boolean(
        string="Permite Imposto de Importação",
        compute="_compute_is_ii_allowed",
    )

    @api.depends("cfop_code_id")
    def _compute_is_ii_allowed(self):
        for record in self:
            if (
                record.cfop_code_id.type_in_out == "in"
                and record.cfop_code_id.destination == "3"
            ):
                record.is_ii_allowed = True
            else:
                record.is_ii_allowed = False

    ii_bc_value = fields.Float(
        string="Valor da Base de Calculo do Imposto de Importação",
        digits=(13, 2),
        compute="_compute_ii_bc_value",
        store=True,
        readonly=False,
    )

    @api.depends("is_ii_allowed")
    def _compute_ii_bc_value(self):
        for record in self:
            if not record.is_ii_allowed:
                record.ii_bc_value = False

    ii_custom_expenses_value = fields.Float(
        string="Valor das Despesas Aduanas e Alfandegárias",
        digits=(13, 2),
        compute="_compute_ii_custom_expenses_value",
        store=True,
        readonly=False,
    )

    @api.depends("is_ii_allowed")
    def _compute_ii_custom_expenses_value(self):
        for record in self:
            if not record.is_ii_allowed:
                record.ii_custom_expenses_value = False

    def domain_ii_tax_id(self):
        return [("tax_domain_id", "=", self.env.ref("l10n_br_fiscal.tax_domain_ii").id)]

    ii_tax_id = fields.Many2one(
        comodel_name="l10n_br_fiscal.tax",
        string="Imposto de Importação",
        domain=domain_ii_tax_id,
        compute="_compute_ii_tax_id",
        store=True,
        readonly=False,
    )

    @api.depends("is_ii_allowed")
    def _compute_ii_tax_id(self):
        for record in self:
            if not record.is_ii_allowed:
                record.ii_tax_id = False

    ii_tax_percent = fields.Float(
        related="ii_tax_id.percent_amount",
        string="Aliquota do Imposto de Importação",
        digits=(3, 4),
        readonly=True,
        store=True,
    )

    ii_value = fields.Float(
        string="Valor do Imposto de Importação",
        digits=(13, 2),
        compute="_compute_ii_value",
        store=True,
        readonly=True,
    )

    @api.depends("ii_bc_value", "ii_tax_percent")
    def _compute_ii_value(self):
        for record in self:
            if not record.is_ii_allowed:
                record.ii_value = False
            else:
                record.ii_value = record.ii_bc_value * record.ii_tax_percent / 100

    @api.constrains("ii_tax_id", "ii_bc_value")
    def _check_ii_bc_value(self):
        for record in self:
            if record.ii_tax_id and not record.ii_bc_value:
                raise ValidationError(
                    _(
                        "Produto: %s - O Valor da Base de Cálculo do Imposto de Importação é obrigatório quando o Imposto de Importação está definido."
                    )
                    % record.product_description
                )

    @api.constrains("ii_tax_id", "ii_custom_expenses_value")
    def _check_ii_custom_expenses_value(self):
        for record in self:
            if record.ii_tax_id and not record.ii_custom_expenses_value:
                raise ValidationError(
                    _(
                        "Produto: %s - O Valor das Despesas Aduaneiras e Alfandegárias é obrigatório quando o Imposto de Importação está definido."
                    )
                    % record.product_description
                )

    # === Grupo UA. Tributos Devolvidos ===
    #  IPI Devolvido

    is_ipi_returned_allowed = fields.Boolean(
        string="Permite IPI Devolvido",
        compute="_compute_is_ipi_returned_allowed",
    )

    @api.depends("emission_finality")
    def _compute_is_ipi_returned_allowed(self):
        for record in self:
            if record.emission_finality == "4":
                record.is_ipi_returned_allowed = True
            else:
                record.is_ipi_returned_allowed = False

    # Valor Total do IPI Devolvido.
    # O motivo da devolução deverá ser informado pela empresa no campo de Informações Adicionais do Produto
    # enquanto o icms vai destacado na nota em caso de devolucao, o ipi nao e destacado
    # e vai nesse campo. Se destacar o ipi, vai gerar debito de ipi pra empresa.
    total_ipi_returned = fields.Float(
        string="Valor Total do IPI Devolvido",
        digits=(13, 2),
    )

    # Percentual da Mercadoria Devolvida
    total_product_returned_percentage = fields.Float(
        string="Percentual da Mercadoria Devolvida",
        digits=(3, 2),
        widget="percentage",
    )

    additional_information = fields.Text(
        related="product_id.fiscal_additional_information",
        string="Informações Adicionais do Produto",
        store=True,
        readonly=True,
    )

    total_for_ibpt_calculation = fields.Float(
        string="Valor Total para Cálculo do IBPT",
        digits=(13, 2),
        compute="_compute_total_for_ibpt_calculation",
        store=True,
        readonly=True,
    )

    @api.depends(
        "total_value",
        "discount_value",
        "icms_deson_value",
        "icms_st_value",
        "icms_st_fcp_value",
        "freight_value",
        "insurance_value",
        "other_expenses_value",
        "ii_value",
        "ipi_value",
    )
    def _compute_total_for_ibpt_calculation(self):
        for record in self:
            record.total_for_ibpt_calculation = (
                record.total_value
                - record.discount_value
                - record.icms_deson_value
                + record.icms_st_value
                + record.icms_st_fcp_value
                + record.freight_value
                + record.insurance_value
                + record.other_expenses_value
                + record.ii_value
                + record.ipi_value
            )

    unit_value_for_ibpt_calculation = fields.Float(
        string="Valor Unitário para Cálculo do IBPT",
        digits=(13, 2),
        compute="_compute_unit_value_for_ibpt_calculation",
        store=True,
        readonly=True,
    )

    @api.depends("total_for_ibpt_calculation", "quantity")
    def _compute_unit_value_for_ibpt_calculation(self):
        for record in self:
            record.unit_value_for_ibpt_calculation = (
                record.total_for_ibpt_calculation / record.quantity
            )

    approximate_federal_tax_amount = fields.Float(
        string="Valor Aproximado do Imposto Federal",
        digits=(13, 2),
        readonly=True,
    )

    approximate_state_tax_amount = fields.Float(
        string="Valor Aproximado do Imposto Estadual",
        digits=(13, 2),
        readonly=True,
    )

    approximate_municipal_tax_amount = fields.Float(
        string="Valor Aproximado do Imposto Municipal",
        digits=(13, 2),
        readonly=True,
    )

    approximate_tax_amount = fields.Float(
        string="Valor Aproximado do Imposto",
        digits=(13, 2),
        compute="_compute_approximate_tax_amount",
        store=True,
        readonly=True,
    )

    ibpt_key = fields.Char(
        string="Chave do IBPT",
        readonly=True,
    )

    @api.depends(
        "approximate_federal_tax_amount",
        "approximate_state_tax_amount",
        "approximate_municipal_tax_amount",
    )
    def _compute_approximate_tax_amount(self):
        for record in self:
            record.approximate_tax_amount = (
                record.approximate_federal_tax_amount
                + record.approximate_state_tax_amount
                + record.approximate_municipal_tax_amount
            )

    def action_fetch_ibpt_taxes(self):
        """
        Fetch approximate tributes from IBPT API for selected lines.
        This method can be called from a button or server action.
        """
        for record in self:
            record._fetch_ibpt_taxes()

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("IBPT"),
                "message": _("Tributos aproximados atualizados com sucesso!"),
                "type": "success",
                "sticky": False,
            },
        }

    # @job(default_channel="root.ibpt")
    # def _job_fetch_ibpt_taxes(self):
    #     """Job to fetch IBPT taxes in background."""
    #     self._fetch_ibpt_taxes()

    def _fetch_ibpt_taxes(self):
        """
        Fetch approximate tributes from IBPT API for this line.
        """
        self.ensure_one()

        local_data = True

        company = self.nfe_id.company_id

        # Get NCM code
        ncm_code = self.product_id.ncm_id.code_unmasked
        ex_tipi = self.product_id.ncm_id.exception
        if not ncm_code:
            raise UserError(
                _("Código NCM não configurado para o produto %s.")
                % self.product_id.name
            )

        # Get UF (state) - from the NFe emitter
        uf = company.partner_id.state_id.code
        if not uf:
            raise UserError(_("UF da empresa não configurada."))

        value_with_discount = self.unit_price - self.unit_discount_value

        # Check if product is imported based on ICMS origin
        # Origins 1, 2, 6, 7 are imported products
        is_imported = self.icms_origin in ("1", "2", "6", "7")

        if local_data:
            tax_rates = self.env["l10n_br_fiscal.ibpt"].get_ibpt_values(
                ncm_code=ncm_code, state_code=uf, ex_tipi=ex_tipi
            )
        else:
            # Get CNPJ from company
            cnpj = company.partner_id.vat
            if not cnpj:
                raise UserError(_("CNPJ da empresa não configurado."))

            # o codigo seguinte faz a requisição, foi revisado e está funcionando em 12/01/2026.
            # mas vamos fazer requisição na base de dados por enquanto.

            # Get IBPT token from company
            token = company.ibpt_token
            if not token:
                raise UserError(
                    _(
                        "Token IBPT não configurado. Configure o token nas configurações da empresa."
                    )
                )

            try:
                # Fetch tax rates from IBPT
                tax_rates = get_ibpt_product_taxes(
                    token=token,
                    cnpj=cnpj,
                    ncm_code=ncm_code,
                    ex_tipi=ex_tipi,
                    uf=uf,
                    description=self.product_description or self.product_id.name,
                    unit=self.unit,
                    value=self.unit_value_for_ibpt_calculation,
                    gtin=self.gtin,
                )

            except IBPTError as e:
                raise UserError(str(e))
            except Exception as e:
                _logger.exception("Error fetching IBPT taxes")
                raise UserError(_("Erro ao buscar tributos do IBPT: %s") % str(e))

        # Calculate tax amounts
        tax_amounts = calculate_approximate_taxes(
            tax_rates=tax_rates,
            value=self.unit_value_for_ibpt_calculation,
            quantity=self.quantity,
            is_imported=is_imported,
        )

        # Update record with calculated values
        self.write(
            {
                "approximate_federal_tax_amount": tax_amounts["federal"],
                "approximate_state_tax_amount": tax_amounts["estadual"],
                "approximate_municipal_tax_amount": tax_amounts["municipal"],
                "ibpt_key": tax_rates["chave"],
            }
        )

        # Explicitly trigger recomputation of parent's total_approx_taxes

        _logger.info(
            f"IBPT taxes fetched for line {self.id}: "
            f"Federal={tax_amounts['federal']}, "
            f"State={tax_amounts['estadual']}, "
            f"Municipal={tax_amounts['municipal']}"
        )
