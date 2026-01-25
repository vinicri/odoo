import logging

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError

# from odoo.addons.queue_job.job import job

from .constants import NFE_EMISSION_FINALITY

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
        # related="product_id.default_code",
        string="Código do Produto",
        readonly=True,
        # required=True,
        # default="CFOP9999",
        store=True,
        size=60,
        compute="_compute_product_code",
    )

    @api.depends("product_id")
    def _compute_product_code(self):
        for record in self:
            if record.product_id:
                record.product_code = record.product_id.default_code  # or "CFOP9999"

    @api.constrains("product_code")
    def _check_product_code(self):
        for record in self:
            if not record.product_code:
                raise ValidationError(_("O Código do Produto é obrigatório."))

    # Preencher com o código GTIN-8, GTIN-12, GTIN-13 ou GTIN-14 (antigos códigos EAN, UPC e DUN-14)
    # Para produtos que não possuem código de barras com GTIN, deve ser informado o literal “SEM GTIN”
    gtin = fields.Char(
        related="product_id.barcode",
        string="Código de Barras",
        store=True,
        size=14,
        readonly=True,
    )

    @api.constrains("gtin")
    def _check_gtin(self):
        for record in self:
            if not record.product_id.no_barcode and not record.gtin:
                raise ValidationError(
                    _(
                        "Verifique o cadastro do produto %s. O produto não está marcado como 'Não possui código de barras' mas o código de barras não foi informado."
                    )
                )
            if record.product_id.no_barcode and record.gtin:
                raise ValidationError(
                    _(
                        "Verifique o cadastro do produto %s. O produto está marcado como 'Não possui código de barras' mas o código de barras foi informado."
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

    @api.depends("product_id", "product_id.name")
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

    # Código CEST (Código Especificador da Substituição Tributária). Opcional.
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
    cfop_code_id = fields.Many2one(
        comodel_name="l10n_br_fiscal.cfop",
        string="CFOP",
        required=True,
    )

    cfop_code = fields.Char(
        related="cfop_code_id.code",
        string="Código CFOP",
        store=True,
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

    @api.onchange("product_id")
    def _onchange_product_id(self):
        for record in self:
            if record.product_id:
                price_dict = record.product_id._price_compute("list_price")
                record.unit_price = price_dict.get(record.product_id.id)
            else:
                record.unit_price = False

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
        related="product_id.barcode",
        string="GTIN da Unidade Tributável",
        store=True,
        size=14,
        readonly=True,
    )

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

    @api.depends("unit_discount_value", "unit_discount_percent")
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

    # esse campo vem do contexto do documento fiscal, do nfe_document xml view.
    emission_finality = fields.Selection(
        NFE_EMISSION_FINALITY,
        string="Finalidade da Emissão",
        required=True,
        readonly=True,
    )

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
            print(record.emission_finality)
            print(record.issuer_id.fiscal_framework)
            if record.emission_finality == "4":
                # Devolução: permite tanto ICMSSN quanto ICMS
                record.icms_allowed_tax_group_ids = tax_group_icms | tax_group_icmssn
            elif not record.issuer_id or not record.issuer_id.fiscal_framework:
                record.icms_allowed_tax_group_ids = False  # empty recordset
            elif record.issuer_id.fiscal_framework in ("1", "2"):
                record.icms_allowed_tax_group_ids = tax_group_icmssn
            else:
                record.icms_allowed_tax_group_ids = tax_group_icms

    # === ICMS ===

    icms_origin = fields.Char(
        related="product_id.icms_origin_id.code",
        string="Origem da Mercadoria",
        size=1,
        # required=True,
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
        # required=True,
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

    # todo colocar na definicao do imposto tax
    icms_bc_modality = fields.Selection(
        string="Modalidade da Base de Calculo",
        selection=[
            ("0", "Margem Valor Agregado (%)"),
            ("1", "Pauta (valor)"),
            ("2", "Preço Tabelado Máximo (valor)"),
            ("3", "Valor da Operação"),
        ],
    )

    # TODO checar se obrigatorio para esses CSTs: 00, 10, 20
    @api.constrains("icms_bc_modality")
    def _check_icms_bc_modality(self):
        for record in self:
            if (
                record.icms_cst_code
                in ("101", "102", "103", "201", "202", "203", "300", "400", "500")
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
            ):
                raise ValidationError(
                    _(
                        f"A modalidade da base de calculo do ICMS é invalido para o item da nota fiscal: {record.product_description}."
                    )
                )

    # no simples é utilizado para devolucao de mercadoria
    icms_bc_value = fields.Float(
        string="Valor da Base de Calculo",
        digits=(13, 2),
    )

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
            if record.icms_bc_value and record.icms_bc_value <= 0:
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

    icms_bc_reduction_percent = fields.Float(
        string="Percentual de Redução da Base de Calculo", digits=(3, 4)
    )

    @api.constrains("icms_bc_reduction_percent")
    def _check_icms_bc_reduction_percent(self):
        for record in self:
            if (
                record.icms_cst_code
                in ("101", "102", "103", "201", "202", "203", "300", "400", "500")
                and record.icms_bc_reduction_percent
            ):
                raise ValidationError(
                    _(
                        f"O CSOSN {record.icms_cst_code} não admite informar o percentual de redução da base de calculo do ICMS para o item da nota fiscal: {record.product_description}."
                    )
                )
            if (
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
        readonly=False,
        store=True,
    )

    @api.constrains("icms_tax_percent")
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
            if record.icms_tax_percent and record.icms_tax_percent <= 0:
                raise ValidationError(
                    _(
                        f"A aliquota do ICMS é invalido para o item da nota fiscal: {record.product_description}."
                    )
                )

    icms_deferment_percent = fields.Float(
        string="Percentual de Diferimento", digits=(3, 4)
    )

    @api.constrains("icms_deferment_percent")
    def _check_icms_deferment_percent(self):
        for record in self:
            if (
                record.icms_cst_code
                in ("101", "102", "103", "201", "202", "203", "300", "400", "500")
                and record.icms_deferment_percent
            ):
                raise ValidationError(
                    _(
                        f"O CSOSN {record.icms_cst_code} não admite informar o percentual de diferimento do ICMS para o item da nota fiscal: {record.product_description}."
                    )
                )

    icms_deferment_value = fields.Float(string="Valor do Diferimento", digits=(13, 2))

    @api.constrains("icms_deferment_value")
    def _check_icms_deferment_value(self):
        for record in self:
            if (
                record.icms_cst_code
                in ("101", "102", "103", "201", "202", "203", "300", "400", "500")
                and record.icms_deferment_value
            ):
                raise ValidationError(
                    _(
                        f"O CSOSN {record.icms_cst_code} não admite informar o valor do diferimento do ICMS para o item da nota fiscal: {record.product_description}."
                    )
                )

    icms_value = fields.Float(
        string="Valor do ICMS",
        digits=(13, 2),
        # compute="_compute_icms_value",
    )

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
            if record.icms_value and record.icms_value <= 0:
                raise ValidationError(
                    _(
                        f"O valor do ICMS é invalido para o item da nota fiscal: {record.product_description}."
                    )
                )

    @api.constrains(
        "icms_bc_modality", "icms_bc_value", "icms_tax_percent", "icms_value"
    )
    def _check_icms_value_required(self):
        for record in self:
            if record.icms_cst_code != "900":
                continue

            icms_fields = [
                record.icms_bc_modality,
                record.icms_bc_value,
                record.icms_tax_percent,
                record.icms_value,
            ]

            # If any ICMS field is set, all fields must be set
            if any(icms_fields) and not all(icms_fields):
                raise ValidationError(
                    _(
                        f"Para o CSOSN 900 se o grupo do ICMS for informado, é obrigatório "
                        f"informar a modalidade da base de calculo, valor da base de calculo, "
                        f"aliquota do ICMS e valor do ICMS. Validação referente ao item da nota "
                        f"fiscal: {record.product_description}."
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

    icms_fcp_tax_id = fields.Many2one(
        comodel_name="l10n_br_fiscal.tax",
        string="FCP",
        domain=_domain_icms_fcp_tax_id,
        # compute="_compute_icms_fcp_tax_id",
    )

    # @api.depends("icms_tax_id")
    # def _compute_icms_fcp_tax_id(self):
    #     icms_sn_group = self.env.ref("l10n_br_fiscal.tax_group_icmssn")
    #     for record in self:
    #         if record.icms_tax_id and record.icms_tax_id.tax_group_id == icms_sn_group:
    #             record.icms_fcp_tax_id = False

    icms_fcp_tax_percent = fields.Float(
        related="icms_fcp_tax_id.percent_amount",
        string="Aliquota do FCP",
        digits=(3, 4),
        store=True,
        readonly=True,
    )

    icms_fcp_bc_value = fields.Float(string="BC FCP`", digits=(13, 2))

    icms_fcp_value = fields.Float(
        string="Valor do FCP", digits=(13, 2), compute="_compute_icms_fcp_value"
    )

    @api.depends("icms_fcp_tax_id", "icms_fcp_bc_value")
    def _compute_icms_fcp_value(self):
        for record in self:
            record.icms_fcp_value = False

    icms_sn_credit_percent = fields.Float(
        string="Aliquota de Crédito do ICMS SN",
        digits=(13, 2),
    )

    @api.constrains("icms_sn_credit_percent")
    def _check_icms_sn_credit_percent(self):
        for record in self:
            if not record.icms_cst_code in ("101", "201"):
                raise ValidationError(
                    _(
                        f"O CSOSN {record.icms_cst_code} não admite informar a aliquota"
                        f" do crédito do ICMS SN ou o valor do crédito do ICMS SN. "
                        f"Validação referente ao item da nota fiscal: {record.product_description}."
                    )
                )

    icms_sn_credit_value = fields.Float(
        string="Valor do Crédito",
        digits=(13, 2),
    )

    @api.constrains("icms_sn_credit_value")
    def _check_icms_sn_credit_value(self):
        for record in self:
            if not record.icms_cst_code in ("101", "201", "900"):
                raise ValidationError(
                    _(
                        f"O CSOSN {record.icms_cst_code} não admite informar o valor do crédito do ICMS SN. "
                        f"Validação referente ao item da nota fiscal: {record.product_description}."
                    )
                )

    @api.constrains("icms_sn_credit_percent", "icms_sn_credit_value")
    def _check_icms_sn_credit_required(self):
        for record in self:
            if record.icms_cst_code != "900":
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

    # @api.depends("icms_tax_id")
    # def _compute_icms_sn_credit(self):
    #     for record in self:
    #         record.icms_sn_credit_percent = False
    #         record.icms_sn_credit_value = False
    # icms_sn_credit_tax = self.env.ref("l10n_br_fiscal.tax_icms_sn_com_credito")
    # icms_sn_credit_tax_st = self.env.ref(
    #     "l10n_br_fiscal.tax_icms_sn_com_credito_st"
    # )
    # for record in self:
    #     if record.icms_tax_id not in (
    #         icms_sn_credit_tax,
    #         icms_sn_credit_tax_st,
    #     ):
    #         record.icms_sn_credit_percent = False
    #         record.icms_sn_credit_value = False

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
    )

    @api.constrains("icms_st_modality")
    def _check_icms_st_modality(self):
        for record in self:
            if record.icms_cst_code in ("201", "202", "203"):
                if not record.icms_st_modality:
                    raise ValidationError(
                        f"Produto: {record.product_description} - Modalidade da Base de Calculo do ICMS ST é obrigatório pro CST {record.icms_cst_code}."
                    )
                else:
                    if record.icms_st_modality not in ("0", "1", "2", "3", "4", "5"):
                        raise ValidationError(
                            f"Produto: {record.product_description} - Modalidade da Base de Calculo do ICMS ST é inválida para o CST {record.icms_cst_code}: {record.icms_st_modality}."
                        )

    icms_st_mva_percent = fields.Float(string="MVA ICMS ST", digits=(3, 4))

    @api.constrains("icms_st_mva_percent")
    def _check_icms_st_mva_percent(self):
        for record in self:
            if record.icms_st_modality == "4" and record.icms_st_mva_percent <= 0:
                raise ValidationError(
                    f"Produto: {record.product_description} - MVA ICMS ST deve ser maior que 0 para a modalidade da Base de Calculo do ICMS ST Margem Valor Agregado (%) {record.icms_st_modality}."
                )

    icms_st_reduction_percent = fields.Float(
        string="Percentual de Redução da Base de Calculo do ICMS ST", digits=(3, 4)
    )

    icms_st_bc_value = fields.Float(
        string="Valor da Base de Calculo do ICMS ST", digits=(13, 2)
    )

    @api.constrains("icms_st_bc_value")
    def _check_icms_st_bc_value(self):
        for record in self:
            if (
                record.icms_tax_id.cst_out_id.code in ("201", "202", "203")
                and record.icms_st_bc_value <= 0
            ):
                if record.icms_st_bc_value <= 0:
                    raise ValidationError(
                        f"Produto: {record.product_description} - Valor da Base de Calculo do ICMS ST deve ser maior que 0 para o CST {record.icms_cst_code}."
                    )

    icms_st_tax_percent = fields.Float(string="Aliquota do ICMS ST", digits=(3, 4))

    @api.constrains("icms_st_tax_percent")
    def _check_icms_st_tax_percent(self):
        for record in self:
            if (
                record.icms_tax_id.cst_out_id.code in ("201", "202", "203")
                and record.icms_st_tax_percent <= 0
            ):
                raise ValidationError(
                    f"Produto: {record.product_description} - Aliquota do ICMS ST deve ser maior que 0 para o CST {record.icms_cst_code}."
                )

    icms_st_value = fields.Float(string="Valor do ICMS ST", digits=(13, 2))

    @api.constrains("icms_st_value")
    def _check_icms_st_value(self):
        for record in self:
            if (
                record.icms_tax_id.cst_out_id.code in ("201", "202", "203")
                and record.icms_st_value <= 0
            ):
                raise ValidationError(
                    f"Produto: {record.product_description} - Valor do ICMS ST deve ser maior que 0 para o CST {record.icms_cst_code}."
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

    @api.constrains("icms_st_fcp_tax_id")
    def _check_icms_st_fcp_tax_id(self):
        for record in self:
            if record.icms_tax_id.cst_out_id.code in ("201", "202", "203"):
                if not record.icms_st_fcp_tax_id:
                    raise ValidationError(
                        f"Produto: {record.product_description} - FCP ST deve ser informado para o CST {record.icms_cst_code}."
                    )

    @api.constrains(
        "icms_st_modality", "icms_st_bc_value", "icms_st_tax_percent", "icms_st_value"
    )
    def _check_icms_st_required(self):
        for record in self:
            if record.icms_cst_code != "900":
                continue

            icms_st_fields = [
                record.icms_st_modality,
                record.icms_st_bc_value,
                record.icms_st_tax_percent,
                record.icms_st_value,
            ]

            # If any ICMS field is set, all fields must be set
            if any(icms_st_fields) and not all(icms_st_fields):
                raise ValidationError(
                    _(
                        f"Para o CSOSN 900 se o grupo do ICMS ST for informado, é obrigatório "
                        f"informar a modalidade da base de calculo ST, valor da base de calculo ST, "
                        f"aliquota do ICMS ST e valor do ICMS ST. Validação referente ao item da nota "
                        f"fiscal: {record.product_description}."
                    )
                )

    icms_st_fcp_tax_percent = fields.Float(
        related="icms_st_fcp_tax_id.percent_amount",
        string="Aliquota do FCP ST",
        digits=(13, 2),
        store=True,
    )

    @api.constrains("icms_st_fcp_tax_percent")
    def _check_icms_st_fcp_tax_percent(self):
        for record in self:
            if (
                record.icms_tax_id.cst_out_id.code in ("201", "202", "203")
                and record.icms_st_fcp_tax_percent <= 0
            ):
                raise ValidationError(
                    f"Produto: {record.product_description} - Aliquota do FCP ST deve ser maior que 0 para o CST {record.icms_cst_code}."
                )

    icms_st_fcp_bc_value = fields.Float(
        string="Valor da Base de Calculo do FCP ST", digits=(13, 2)
    )

    @api.constrains("icms_st_fcp_bc_value")
    def _check_icms_st_fcp_bc_value(self):
        for record in self:
            if (
                record.icms_tax_id.cst_out_id.code in ("201", "202", "203")
                and record.icms_st_fcp_bc_value <= 0
            ):
                raise ValidationError(
                    f"Produto: {record.product_description} - Valor da Base de Calculo do FCP ST deve ser maior que 0 para o CST {record.icms_cst_code}."
                )

    icms_st_fcp_value = fields.Float(string="Valor do FCP ST", digits=(13, 2))

    @api.constrains("icms_st_fcp_value")
    def _check_icms_st_fcp_value(self):
        for record in self:
            if (
                record.icms_tax_id.cst_out_id.code in ("201", "202", "203")
                and record.icms_st_fcp_value <= 0
            ):
                raise ValidationError(
                    f"Produto: {record.product_description} - Valor do FCP ST deve ser maior que 0 para o CST {record.icms_cst_code}."
                )

    @api.constrains(
        "icms_st_fcp_tax_percent", "icms_st_fcp_bc_value", "icms_st_fcp_value"
    )
    def _check_icms_st_fcp_required(self):
        for record in self:
            if record.icms_cst_code != "900":
                continue

            icms_st_fcp_fields = [
                record.icms_st_fcp_tax_percent,
                record.icms_st_fcp_bc_value,
                record.icms_st_fcp_value,
            ]

            if any(icms_st_fcp_fields) and not all(icms_st_fcp_fields):
                raise ValidationError(
                    _(
                        f"Para o CSOSN 900 se o grupo do FCP ST for informado, é obrigatório "
                        f"informar a aliquota do FCP ST, valor da base de calculo do FCP ST e valor do FCP ST. Validação referente ao item da nota "
                        f"fiscal: {record.product_description}."
                    )
                )

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

    icms_deson_value = fields.Float(
        string="Valor do ICMS Desoneração",
        digits=(13, 2),
    )

    icms_deson_reason = fields.Many2one(
        comodel_name="l10n_br_fiscal.icms.deson.reason",
        string="Motivo da Desoneração do ICMS",
        domain="[('cst_ids', 'in', icms_cst_id)]",
    )

    @api.constrains("icms_deson_reason", "icms_deson_value")
    def _check_icms_deson_required(self):
        for record in self:
            if record.icms_deson_reason and not record.icms_deson_value:
                raise ValidationError(
                    _(
                        "Produto: %s - O Valor do ICMS Desoneração é obrigatório quando o Motivo da Desoneração do ICMS está definido."
                    )
                    % record.product_description
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

    # === ICMS Desoneração ===
    # Não implementado
    # valor icms desonarado
    # motivo de desoneração do icms

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

    # utilizando o padrao, depois implementar conforme seção 8.9 do MOC – Visão Geral (Tabela do Código de Enquadramento do IPI)
    # default 999 para outros produtos
    # Informar apenas quando o item for sujeito ao IPI
    ipi_guideline_code = fields.Char(string="Código de Enquadramento", size=3)

    def _is_issuer_simples_nacional(self):
        return self.issuer_id.fiscal_framework in ("1", "2")

    def _issuer_contributes_to_ipi(self):
        return self.issuer_id.ipi_contributes

    # empresa do simples utilizar ipi de saida 99 com valor zero quando for contruibinte do ipi - 99 outras saidas
    # simples NAO contribuinte do ipi e empresa no regime normal que nao tributa ipi (comercio) utilizar ipi de saida 53 - saida nao tributada
    # devolucao de mercadoria utilizar 53
    # industria utilizar os outros CST apropriados
    # def _domain_ipi_tax_id(self):
    #     if not self._issuer_contributes_to_ipi():
    #         return [("cst_out_id", "=", "cst_ipi_53")]
    #     if self._is_issuer_simples_nacional():
    #         return [("cst_out_id", "=", "cst_ipi_99")]
    #     else:
    #         return [("tax_group_id", "=", "tax_group_ipi")]

    forced_ipi_tax_id = fields.Many2one(
        comodel_name="l10n_br_fiscal.tax",
        string="IPI",
        compute="_compute_forced_ipi_tax_id",
    )

    @api.depends("issuer_id", "issuer_id.fiscal_framework", "issuer_id.ipi_contributes")
    def _compute_forced_ipi_tax_id(self):
        for record in self:
            if record._is_issuer_simples_nacional():
                if record._issuer_contributes_to_ipi():
                    record.forced_ipi_tax_id = record.env.ref(
                        "l10n_br_fiscal.tax_ipi_outros"
                    ).id
                else:
                    record.forced_ipi_tax_id = record.env.ref(
                        "l10n_br_fiscal.tax_ipi_nt"
                    ).id
            else:
                record.forced_ipi_tax_id = False

    def _default_ipi_tax_id(self):
        if self._is_issuer_simples_nacional():
            if self._issuer_contributes_to_ipi():
                return self.env.ref("l10n_br_fiscal.tax_ipi_outros")
            else:
                return self.env.ref("l10n_br_fiscal.tax_ipi_nt")
        else:
            return False

    def _domain_ipi_tax_id(self):
        return [("tax_group_id", "=", self.env.ref("l10n_br_fiscal.tax_group_ipi").id)]

    ipi_tax_id = fields.Many2one(
        comodel_name="l10n_br_fiscal.tax",
        string="IPI",
        compute="_compute_ipi_tax_id",
        domain=_domain_ipi_tax_id,
        store=True,
    )

    @api.depends("forced_ipi_tax_id")
    def _compute_ipi_tax_id(self):
        for record in self:
            record.ipi_tax_id = record.forced_ipi_tax_id

    # empresa do simples utilizar ipi de saida 99 com valor zero quando for contruibinte do ipi
    # simples NAO contribuinte do ipi e empresa no regime normal que nao tributa ipi (comercio) utilizar ipi de saida 53
    # devolucao de mercadoria utilizar 53
    # industria utilizar os outros CST apropriados
    ipi_cst_id = fields.Many2one(
        related="ipi_tax_id.cst_out_id",
        string="CST IPI",
        readonly=True,
        # required=True,
    )

    ipi_cst = fields.Char(
        related="ipi_cst_id.code", string="CST IPI", size=2, store=True, readonly=True
    )

    ipi_tax_percent = fields.Float(
        related="ipi_tax_id.percent_amount",
        string="Aliquota",
        digits=(3, 4),
        readonly=True,
        store=True,
    )

    ipi_bc_value = fields.Float(
        string="Valor da Base de Calculo do IPI",
        digits=(13, 2),
        compute="_compute_ipi_bc_value",
        readonly=True,
    )

    @api.depends("issuer_id.fiscal_framework")
    def _compute_ipi_bc_value(self):
        for record in self:
            if record._is_issuer_simples_nacional():
                record.ipi_bc_value = 0.00
            else:
                record.ipi_bc_value = False

    ipi_value = fields.Float(
        string="Valor do IPI",
        digits=(13, 2),
        readonly=True,
        compute="_compute_ipi_value",
    )

    @api.depends("ipi_bc_value", "ipi_tax_percent")
    def _compute_ipi_value(self):
        for record in self:
            record.ipi_value = record.ipi_bc_value * record.ipi_tax_percent / 100

    ipi_unit_value = fields.Float(string="Valor na Unidade Tributavel", digits=(13, 2))

    ipi_unit_quantity = fields.Float(
        string="Quantidade na Unidade Tributavel", digits=(13, 4)
    )

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

    is_simples_nacional = fields.Boolean(
        string="Simples Nacional",
        compute="_compute_is_simples_nacional",
        readonly=True,
    )

    @api.depends("issuer_id", "issuer_id.fiscal_framework")
    def _compute_is_simples_nacional(self):
        for record in self:
            record.is_simples_nacional = record._is_issuer_simples_nacional()

    pis_tax_id = fields.Many2one(
        comodel_name="l10n_br_fiscal.tax",
        string="PIS",
        compute="_compute_pis_tax_id",
        store=True,
        domain="[('tax_group_id', '=', 'tax_group_pis')]",
        readonly=False,
    )

    @api.depends("is_simples_nacional")
    def _compute_pis_tax_id(self):
        for record in self:
            if record.is_simples_nacional:
                record.pis_tax_id = record.env.ref(
                    "l10n_br_fiscal.tax_pis_outras_operacoes"
                ).id
            else:
                record.pis_tax_id = False

    pis_cst_id = fields.Many2one(
        related="pis_tax_id.cst_out_id",
        string="CST PIS",
        readonly=True,
        store=True,
        # required=True,
    )

    pis_cst = fields.Char(
        related="pis_cst_id.code",
        string="CST PIS",
        size=2,
        store=True,
        readonly=True,
    )

    pis_tax_percent = fields.Float(
        related="pis_tax_id.percent_amount",
        store=True,
        string="Aliquota do PIS",
        digits=(3, 4),
    )

    pis_bc_value = fields.Float(
        string="Valor da Base de Calculo do PIS",
        digits=(13, 2),
        readonly=True,
        store=True,
        compute="_compute_pis_bc_value",
    )

    @api.depends("is_simples_nacional")
    def _compute_pis_bc_value(self):
        for record in self:
            if record.is_simples_nacional:
                record.pis_bc_value = 0.00
            else:
                record.pis_bc_value = False

    pis_value = fields.Float(
        string="Valor do PIS",
        digits=(13, 2),
        readonly=True,
        store=True,
        compute="_compute_pis_value",
    )

    @api.depends("pis_bc_value", "pis_tax_percent")
    def _compute_pis_value(self):
        for record in self:
            record.pis_value = record.pis_bc_value * record.pis_tax_percent / 100

    pis_bc_quantity = fields.Float(
        string="Quantidade (Tributado por quantidade)", digits=(12, 4)
    )

    pis_tax_quantity = fields.Float(
        string="Aliquota em reais (Tributado por quantidade)", digits=(11, 4)
    )
    # cst
    # base de calculo
    # aliquota em percentual
    # quantidade vendida
    # aliquota em valor
    # valor

    # ===  pis st ===

    pis_st_tax_id = fields.Many2one(
        comodel_name="l10n_br_fiscal.tax",
        string="PIS ST",
        domain=[("tax_group_id", "=", "tax_group_pis_st")],
        readonly=False,
        compute="_compute_pis_st_tax_id",
        store=True,
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

    pis_st_tax_percent = fields.Float(
        related="pis_st_tax_id.percent_amount",
        string="Aliquota do PIS ST",
        digits=(3, 4),
        readonly=True,
        store=True,
    )

    pis_st_bc_value = fields.Float(
        string="Valor da Base de Calculo do PIS ST",
        digits=(13, 2),
        readonly=True,
        compute="_compute_pis_st_bc_value",
        store=True,
    )

    def _compute_pis_st_bc_value(self):
        for record in self:
            record.pis_st_bc_value = False

    pis_st_bc_quantity = fields.Float(
        string="Quantidade PIS ST (Tributado por quantidade)", digits=(12, 4)
    )

    pis_st_tax_quantity = fields.Float(
        string="Aliquota em reais PIS ST (Tributado por quantidade)", digits=(11, 4)
    )

    pis_st_value = fields.Float(
        string="Valor do PIS ST",
        digits=(13, 2),
        compute="_compute_pis_st_value",
        store=True,
        readonly=True,
    )

    def _compute_pis_st_value(self):
        for record in self:
            record.pis_st_value = False

    # base de calculo
    # aliquota em percentual
    # aliquota em valor
    # quantidade vendida
    # valor do pis st

    # ===  cofins ===

    cofins_tax_id = fields.Many2one(
        comodel_name="l10n_br_fiscal.tax",
        string="COFINS",
        domain="[('tax_group_id', '=', 'tax_group_cofins')]",
        readonly=False,
        store=True,
        compute="_compute_cofins_tax_id",
    )

    @api.depends("is_simples_nacional")
    def _compute_cofins_tax_id(self):
        for record in self:
            if record.is_simples_nacional:
                record.cofins_tax_id = record.env.ref(
                    "l10n_br_fiscal.tax_cofins_outras_operacoes"
                ).id
            else:
                record.cofins_tax_id = False

    cofins_cst_id = fields.Many2one(
        related="cofins_tax_id.cst_out_id",
        string="CST COFINS",
        readonly=True,
        # required=True,
        store=True,
    )

    cofins_cst = fields.Char(
        related="cofins_cst_id.code",
        string="CST COFINS",
        size=2,
        store=True,
        readonly=True,
    )

    cofins_tax_percent = fields.Float(
        related="cofins_tax_id.percent_amount",
        string="Aliquota do COFINS",
        digits=(3, 4),
        store=True,
        readonly=True,
    )

    cofins_bc_value = fields.Float(
        string="Valor da Base de Calculo do COFINS",
        digits=(13, 2),
        store=True,
        compute="_compute_cofins_bc_value",
        readonly=True,
    )

    @api.depends("is_simples_nacional")
    def _compute_cofins_bc_value(self):
        for record in self:
            if record.is_simples_nacional:
                record.cofins_bc_value = 0.00
            else:
                record.cofins_bc_value = False

    cofins_bc_quantity = fields.Float(
        string="Quantidade COFINS (Tributado por quantidade)", digits=(12, 4)
    )

    cofins_tax_quantity = fields.Float(
        string="Aliquota em reais COFINS (Tributado por quantidade)", digits=(11, 4)
    )

    cofins_value = fields.Float(
        string="Valor do COFINS",
        digits=(13, 2),
        store=True,
        compute="_compute_cofins_value",
        readonly=True,
    )

    @api.depends("cofins_bc_value", "cofins_tax_percent")
    def _compute_cofins_value(self):
        for record in self:
            record.cofins_value = (
                record.cofins_bc_value * record.cofins_tax_percent / 100
            )

    # base de calculo
    # aliquota em percentual
    # valor do cofins
    # quantidade vendida
    # aliquota em valor

    # ===  cofins st ===

    cofins_st_tax_id = fields.Many2one(
        comodel_name="l10n_br_fiscal.tax",
        string="COFINS ST",
        domain=[("tax_group_id", "=", "tax_group_cofins_st")],
        readonly=False,
        store=True,
        compute="_compute_cofins_st_tax_id",
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

    cofins_st_tax_percent = fields.Float(
        related="cofins_st_tax_id.percent_amount",
        string="Aliquota do COFINS ST",
        digits=(3, 4),
        readonly=True,
        store=True,
    )

    cofins_st_bc_value = fields.Float(
        string="Valor da Base de Calculo do COFINS ST",
        digits=(13, 2),
        store=True,
        compute="_compute_cofins_st_bc_value",
        readonly=True,
    )

    def _compute_cofins_st_bc_value(self):
        for record in self:
            record.cofins_st_bc_value = False

    cofins_st_bc_quantity = fields.Float(
        string="Quantidade COFINS ST (Tributado por quantidade)", digits=(12, 4)
    )

    cofins_st_tax_quantity = fields.Float(
        string="Aliquota em reais COFINS ST (Tributado por quantidade)", digits=(11, 4)
    )

    cofins_st_value = fields.Float(
        string="Valor do COFINS ST",
        digits=(13, 2),
        store=True,
        compute="_compute_cofins_st_value",
        readonly=True,
    )

    def _compute_cofins_st_value(self):
        for record in self:
            record.cofins_st_value = False

    # base de calculo
    # aliquota em percentual
    # aliquota em valor
    # quantidade vendida
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

    ii_bc_value = fields.Float(
        string="Valor da Base de Calculo do Imposto de Importação",
        digits=(13, 2),
    )

    ii_custom_expenses_value = fields.Float(
        string="Valor das Despesas Aduanas e Alfandegárias",
        digits=(13, 2),
    )

    ii_tax_id = fields.Many2one(
        comodel_name="l10n_br_fiscal.tax",
        string="Imposto de Importação",
        domain=[("tax_domain", "=", "ii")],
    )

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
