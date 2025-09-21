from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


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

        return super().create(vals)

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
        string="Código do Produto/Serviço",
        readonly=True,
        required=True,
        # default="CFOP9999",
        store=True,
        size=60,
        compute="_compute_product_code",
    )

    @api.depends("product_id")
    def _compute_product_code(self):
        for record in self:
            record.product_code = record.product_id.default_code or "CFOP9999"

    @api.constrains("product_code")
    def _check_product_code(self):
        for record in self:
            if record.product_code:
                raise ValidationError(_("O Código do Produto é obrigatório."))

    # Preencher com o código GTIN-8, GTIN-12, GTIN-13 ou GTIN-14 (antigos códigos EAN, UPC e DUN-14)
    # Para produtos que não possuem código de barras com GTIN, deve ser informado o literal “SEM GTIN”
    gtin = fields.Char(
        related="product_id.barcode",
        compute="_compute_gtin",
        string="GTIN",
        store=True,
        size=14,
        required=True,
        readonly=True,
    )

    @api.depends("product_id")
    def _compute_gtin(self):
        for record in self:
            record.gtin = record.product_id.barcode

    # Descrição do produto ou serviço.
    # Para NFC-e em homologação, a descrição do primeiro item deve ser "NOTA FISCAL EMITIDA EM AMBIENTE DE HOMOLOGACAO - SEM VALOR FISCAL".
    product_description = fields.Char(
        related="product_id.name",
        string="Descrição do Produto/Serviço",
        required=True,
        size=120,
        store=True,
    )

    @api.constrains("product_description")
    def _check_product_description(self):
        for record in self:
            if record.product_description:
                raise ValidationError(_("A Descrição do Produto é obrigatória."))

    # Código NCM com 8 dígitos. Obrigatório.
    # Para serviço ou item sem produto, informar “00” (dois zeros)
    ncm_code = fields.Char(
        related="product_id.ncm_id.code",
        string="NCM",
        required=True,
        size=8,
        store=True,
        readonly=True,
    )

    @api.constrains("ncm_code")
    def _check_ncm_code(self):
        for record in self:
            if record.ncm_code:
                raise ValidationError(_("O Código NCM é obrigatório."))

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
        string="CFOP",
        required=True,
        size=4,
        store=True,
        readonly=True,
    )

    # Unidade Comercial. Informar a unidade de comercialização do produto.
    # NFC-e com unidade de comercialização inválida é rejeitada.
    unit = fields.Char(
        related="product_id.uom_id.nfe_name",
        string="Unidade de Venda",
        required=True,
        readonly=True,
        size=6,
        store=True,
    )

    # Informar a quantidade de comercialização do produto.
    quantity = fields.Float(
        string="Quantidade de Venda", required=True, digits=(11, 4), default=1
    )

    # Valor Unitário de Comercialização do produto, informativo (0-10 decimais). [48, 49]
    unit_value = fields.Float(
        string="Valor Unitário",
        readonly=False,
        required=True,
        digits=(11, 10),
    )

    @api.onchange("product_id")
    def _onchange_product_id(self):
        for record in self:
            price = record.product_id.pricelist._get_product_price(
                record.product_id, 1.0
            )
            record.unit_value = price[record.product_id.id][0]

    # Valor Total Bruto do Produto/Serviço.
    # O valor do ICMS faz parte do Valor Total Bruto
    total_value = fields.Float(
        compute="_compute_total_value",
        string="Valor Total Bruto do Produto/Serviço",
        required=True,
        digits=(13, 2),
        readonly=True,
        store=True,
    )

    @api.depends("unit_value", "quantity")
    def _compute_total_value(self):
        for record in self:
            record.total_value = (
                record.commercial_unit_value * record.commercial_quantity
            )

    # O GTIN da unidade tributável deve corresponder àquele da menor unidade comercializável identificada por código GTIN.
    # Para produtos que não possuem código de barras com GTIN, deve ser informado o literal "SEM GTIN”
    # Obrigatório.
    gtin_trib = fields.Char(
        related="product_id.barcode",
        compute="_compute_gtin",
        string="GTIN da Unidade Tributável",
        store=True,
        size=14,
        required=True,
        readonly=True,
    )

    # Unidade Tributável. Obrigatório.
    unit_trib = fields.Char(
        related="product_id.uom_id.nfe_name",
        string="Unidade Tributável",
        required=True,
        readonly=True,
        size=6,
        store=True,
    )

    # Quantidade Tributável. Obrigatório.
    quantity_trib = fields.Float(
        string="Quantidade Tributável",
        compute="_compute_quantity_trib",
        required=True,
        readonly=True,
        digits=(11, 4),
    )

    @api.depends("quantity")
    def _compute_quantity_trib(self):
        for record in self:
            record.quantity_trib = record.quantity

    unit_value_trib = fields.Float(
        string="Valor Unitário",
        readonly=True,
        required=True,
        digits=(11, 10),
        compute="_compute_unit_value_trib",
    )

    @api.depends("unit_value")
    def _compute_unit_value_trib(self):
        for record in self:
            record.unit_value_trib = record.unit_value

    # Valor Total do Frete do item. Opcional.
    freight_value = fields.Float(string="Valor do Frete do Item", digits=(13, 2))

    # Valor Total do Seguro do item. Opcional.
    insurance_value = fields.Float(string="Valor do Seguro do Item", digits=(13, 2))

    # Valor do Desconto do item. Opcional.
    discount_value = fields.Float(string="Valor do Desconto do Item", digits=(13, 2))

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

    # ===  impostos ===

    # === ICMS ===

    icms_origin = fields.Char(
        related="product_id.icms_origin_id.code",
        string="Origem da Mercadoria",
        size=1,
        required=True,
        store=True,
        readonly=True,
    )

    # 1 - Simples Nacional
    # 2 - Simples Nacional – excesso de sublimite da receita bruta
    # 3 - Regime Normal
    def _domain_icms_tax_id(self):
        if (
            self.nfe_id.issuer_id.fiscal_framework == "1"
            or self.nfe_id.issuer_id.fiscal_framework == "2"
        ):
            return [("tax_group_id", "=", "tax_group_icmssn")]
        return [
            "|",
            ("tax_group_id", "=", "tax_group_icms"),
            ("tax_group_id", "=", "tax_group_icmsst"),
        ]

    icms_tax_id = fields.Many2one(
        comodel_name="l10n_br_fiscal.tax",
        string="Imposto",
        domain=_domain_icms_tax_id,
        # domain=[('cst_out_id', '=', icms_cst_id)],
        required=True,
    )

    icms_cst_id = fields.Many2one(
        related="icms_tax_id.cst_out_id",
        string="CST ICMS",
        readonly=True,
        required=True,
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
        related="icms_cst_id.code",
        string="CST ICMS",
        size=3,
        store=True,
        readonly=True,
    )

    @api.depends("icms_cst_id", "icms_origin")
    def _compute_icms_cst(self):
        for record in self:
            if record.icms_origin and record.icms_cst_id:
                record.icms_cst = f"{record.icms_cst_id.code}{record.icms_origin}"
            else:
                record.icms_cst = False

    # todo colocar na definicao do imposto tax
    icms_bc_modality = fields.Selection(
        string="Modalidade da Base de Calculo",
        selection=[
            ("0", "Margem Valor Agregado (%)"),
            ("1", "Pauta (valor)"),
            ("2", "Preço Tabelado Máximo (valor)"),
            ("3", "Valor da Operação"),
        ],
        default="3",
    )

    icms_tax_percent = fields.Float(
        related="icms_tax_id.percent_amount",
        string="Aliquota",
        digits=(3, 4),
        readonly=True,
        store=True,
    )

    icms_bc_reduction_percent = fields.Float(
        string="Percentual de Redução da Base de Calculo", digits=(3, 4)
    )

    icms_bc_value = fields.Float(
        string="Valor da Base de Calculo",
        digits=(13, 2),
        compute="_compute_icms_bc_value",
        store=True,
    )

    def _compute_icms_bc_value(self):
        for record in self:
            record.icms_bc_value = False

    icms_deferment_percent = fields.Float(
        string="Percentual de Diferimento", digits=(3, 4)
    )

    icms_deferment_value = fields.Float(string="Valor do Diferimento", digits=(13, 2))

    icms_value = fields.Float(
        string="Valor do ICMS",
        digits=(13, 2),
        compute="_compute_icms_value",
        store=True,
    )

    @api.depends("icms_tax_id", "icms_bc_value")
    def _compute_icms_value(self):
        for record in self:
            record.icms_value = False
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

    icms_fcp_tax_id = fields.Many2one(
        comodel_name="l10n_br_fiscal.tax",
        string="Imposto",
        domain=[("tax_group_id", "=", "tax_group_icmsfcp")],
        compute="_compute_icms_fcp_tax_id",
    )

    @api.depends("icms_tax_id")
    def _compute_icms_fcp_tax_id(self):
        icms_sn_group = self.env.ref("l10n_br_fiscal.tax_group_icmssn")
        for record in self:
            if record.icms_tax_id.tax_group_id == icms_sn_group:
                record.icms_fcp_tax_id = False

    icms_fcp_tax_percent = fields.Float(
        related="icms_fcp_tax_id.percent_amount",
        string="Imposto",
        digits=(3, 4),
        store=True,
        readonly=True,
    )

    icms_fcp_bc_value = fields.Float(string="Valor da Base de Calculo", digits=(13, 2))

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
        compute="_compute_icms_sn_credit",
    )

    icms_sn_credit_value = fields.Float(
        string="Valor do Crédito",
        digits=(13, 2),
        compute="_compute_icms_sn_credit",
    )

    @api.depends("icms_tax_id")
    def _compute_icms_sn_credit(self):
        for record in self:
            record.icms_sn_credit_percent = False
            record.icms_sn_credit_value = False
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

    icms_st_mva_percent = fields.Float(string="MVA ICMS ST", digits=(3, 4))

    icms_st_reduction_percent = fields.Float(
        string="Percentual de Redução da Base de Calculo do ICMS ST", digits=(3, 4)
    )

    icms_st_bc_value = fields.Float(
        string="Valor da Base de Calculo do ICMS ST", digits=(13, 2)
    )

    icms_st_tax_percent = fields.Float(string="Aliquota do ICMS ST", digits=(3, 4))

    icms_st_value = fields.Float(string="Valor do ICMS ST", digits=(13, 2))

    icms_st_fcp_tax_id = fields.Many2one(
        comodel_name="l10n_br_fiscal.tax",
        string="Imposto",
        domain=[("tax_group_id", "=", "tax_group_icmsfcp_st")],
    )

    icms_st_fcp_tax_percent = fields.Float(
        related="icms_st_fcp_tax_id.percent_amount",
        string="Imposto",
        digits=(13, 2),
        store=True,
    )

    icms_st_fcp_bc_value = fields.Float(
        string="Valor da Base de Calculo do FCP ST", digits=(13, 2)
    )

    icms_st_fcp_value = fields.Float(string="Valor do FCP ST", digits=(13, 2))

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

    # ===  ipi ===

    # utilizando o padrao, depois implementar conforme seção 8.9 do MOC – Visão Geral (Tabela do Código de Enquadramento do IPI)
    # default 999 para outros produtos
    ipi_guideline_code = fields.Char(string="Código de Enquadramento", size=3)

    def _is_issuer_simples_nacional(self):
        return self.nfe_id.issuer_id.fiscal_framework in ("1", "2")

    def _issuer_contributes_to_ipi(self):
        return self.nfe_id.issuer_id.ipi_contributes

    # empresa do simples utilizar ipi de saida 99 com valor zero quando for contruibinte do ipi
    # simples NAO contribuinte do ipi e empresa no regime normal que nao tributa ipi (comercio) utilizar ipi de saida 53
    # devolucao de mercadoria utilizar 53
    # industria utilizar os outros CST apropriados
    def _domain_ipi_tax_id(self):
        if not self._issuer_contributes_to_ipi():
            return [("cst_out_id", "=", "cst_ipi_53")]
        if self._is_issuer_simples_nacional():
            return [("cst_out_id", "=", "cst_ipi_99")]
        else:
            return [("tax_group_id", "=", "tax_group_ipi")]

    def _default_ipi_tax_id(self):
        if not self._issuer_contributes_to_ipi():
            return self.env.ref("l10n_br_fiscal.tax_ipi_nt")
        if self._is_issuer_simples_nacional():
            return self.env.ref("l10n_br_fiscal.tax_ipi_outros")
        else:
            return False

    ipi_tax_id = fields.Many2one(
        comodel_name="l10n_br_fiscal.tax",
        string="IPI",
        domain=_domain_ipi_tax_id,
        default=_default_ipi_tax_id,
    )

    # empresa do simples utilizar ipi de saida 99 com valor zero quando for contruibinte do ipi
    # simples NAO contribuinte do ipi e empresa no regime normal que nao tributa ipi (comercio) utilizar ipi de saida 53
    # devolucao de mercadoria utilizar 53
    # industria utilizar os outros CST apropriados
    ipi_cst_id = fields.Many2one(
        related="ipi_tax_id.cst_out_id",
        string="CST IPI",
        readonly=True,
        required=True,
    )

    ipi_cst = fields.Char(
        related="ipi_cst_id.code", string="CST IPI", size=2, store=True, readonly=True
    )

    ipi_tax_percent = fields.Float(
        string="Aliquota do IPI",
        digits=(13, 2),
        compute="_compute_ipi_tax_percent",
        store=True,
    )

    #        related="ipi_tax_id.percent_amount",

    def _compute_ipi_tax_percent(self):
        for record in self:
            if self._is_issuer_simples_nacional():
                record.ipi_tax_percent = 0.00
            else:
                record.ipi_tax_percent = record.ipi_tax_id.percent_amount

    def _default_ipi_bc_value(self):
        if not self._issuer_contributes_to_ipi():
            return False
        if self._is_issuer_simples_nacional():
            return 0.00
        else:
            return False

    ipi_bc_value = fields.Float(
        string="Valor da Base de Calculo do IPI",
        digits=(13, 2),
        default=_default_ipi_bc_value,
    )

    def _default_ipi_value(self):
        if not self._issuer_contributes_to_ipi():
            return False
        if self._is_issuer_simples_nacional():
            return 0.00
        else:
            return False

    ipi_value = fields.Float(
        string="Valor do IPI", digits=(13, 2), default=_default_ipi_value
    )

    # @api.onchange("ipi_tax_id")
    # def _onchange_ipi_tax_id(self):
    #     for record in self:
    #         if not record._issuer_contributes_to_ipi():
    #             record.ipi_bc_value = False
    #             record.ipi_value = False
    #         if record._is_issuer_simples_nacional():
    #             record.ipi_bc_value = 0.00
    #             record.ipi_value = 0.00
    #         else:
    #             record.ipi_bc_value = False
    #             record.ipi_value = False

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

    def _domain_pis_tax_id(self):
        if self._is_issuer_simples_nacional():
            return [("cst_out_id", "=", "cst_pis_99")]
        else:
            return [("tax_group_id", "=", "tax_group_pis")]

    def _default_pis_tax_id(self):
        if self._is_issuer_simples_nacional():
            return self.env.ref("l10n_br_fiscal.tax_pis_outras_operacoes")
        else:
            return False

    pis_tax_id = fields.Many2one(
        comodel_name="l10n_br_fiscal.tax",
        string="PIS",
        domain=_domain_pis_tax_id,
        default=_default_pis_tax_id,
    )

    pis_cst_id = fields.Many2one(
        related="pis_tax_id.cst_out_id",
        string="CST PIS",
        readonly=True,
        required=True,
    )

    pis_cst = fields.Char(
        related="pis_cst_id.code", string="CST PIS", size=2, store=True, readonly=True
    )

    @api.depends("pis_tax_id")
    def _compute_pis_tax_percent(self):
        for record in self:
            if self._is_issuer_simples_nacional():
                record.pis_tax_percent = 0.00
            else:
                record.pis_tax_percent = record.pis_tax_id.percent_amount

    pis_tax_percent = fields.Float(
        string="Aliquota do PIS",
        digits=(3, 4),
        compute="_compute_pis_tax_percent",
        store=True,
    )

    def _default_pis_bc_value(self):
        if self._is_issuer_simples_nacional():
            return 0.00
        else:
            return False

    pis_bc_value = fields.Float(
        string="Valor da Base de Calculo do PIS",
        digits=(13, 2),
        default=_default_pis_bc_value,
    )

    pis_bc_quantity = fields.Float(
        string="Quantidade (Tributado por quantidade)", digits=(12, 4)
    )

    pis_tax_quantity = fields.Float(
        string="Aliquota em reais (Tributado por quantidade)", digits=(11, 4)
    )

    def _default_pis_value(self):
        if self._is_issuer_simples_nacional():
            return 0.00
        else:
            return False

    pis_value = fields.Float(
        string="Valor do PIS", digits=(13, 2), default=_default_pis_value
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
    )

    pis_st_cst_id = fields.Many2one(
        related="pis_st_tax_id.cst_out_id",
        string="CST PIS ST",
        readonly=True,
        required=True,
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
        store=True,
    )

    pis_st_bc_value = fields.Float(
        string="Valor da Base de Calculo do PIS ST", digits=(13, 2)
    )

    pis_st_bc_quantity = fields.Float(
        string="Quantidade PIS ST (Tributado por quantidade)", digits=(12, 4)
    )

    pis_st_tax_quantity = fields.Float(
        string="Aliquota em reais PIS ST (Tributado por quantidade)", digits=(11, 4)
    )

    pis_st_value = fields.Float(string="Valor do PIS ST", digits=(13, 2))

    # base de calculo
    # aliquota em percentual
    # aliquota em valor
    # quantidade vendida
    # valor do pis st

    # ===  cofins ===

    def _domain_cofins_tax_id(self):
        if self._is_issuer_simples_nacional():
            return [("cst_out_id", "=", "cst_cofins_99")]
        else:
            return [("tax_group_id", "=", "tax_group_cofins")]

    def _default_cofins_tax_id(self):
        if self._is_issuer_simples_nacional():
            return self.env.ref("l10n_br_fiscal.tax_cofins_outras_operacoes")
        else:
            return False

    cofins_tax_id = fields.Many2one(
        comodel_name="l10n_br_fiscal.tax",
        string="COFINS",
        domain=_domain_cofins_tax_id,
        default=_default_cofins_tax_id,
    )

    cofins_cst_id = fields.Many2one(
        related="cofins_tax_id.cst_out_id",
        string="CST COFINS",
        readonly=True,
        required=True,
    )

    cofins_cst = fields.Char(
        related="cofins_cst_id.code",
        string="CST COFINS",
        size=2,
        store=True,
        readonly=True,
    )

    def _default_cofins_tax_percent(self):
        if self._is_issuer_simples_nacional():
            return 0.00
        else:
            return False

    cofins_tax_percent = fields.Float(
        related="cofins_tax_id.percent_amount",
        string="Aliquota do COFINS",
        digits=(3, 4),
        default=_default_cofins_tax_percent,
        store=True,
    )

    def _default_cofins_bc_value(self):
        if self._is_issuer_simples_nacional():
            return 0.00
        else:
            return False

    cofins_bc_value = fields.Float(
        string="Valor da Base de Calculo do COFINS",
        digits=(13, 2),
        default=_default_cofins_bc_value,
    )

    cofins_bc_quantity = fields.Float(
        string="Quantidade COFINS (Tributado por quantidade)", digits=(12, 4)
    )

    cofins_tax_quantity = fields.Float(
        string="Aliquota em reais COFINS (Tributado por quantidade)", digits=(11, 4)
    )

    def _default_cofins_value(self):
        if self._is_issuer_simples_nacional():
            return 0.00
        else:
            return False

    cofins_value = fields.Float(
        string="Valor do COFINS",
        digits=(13, 2),
        default=_default_cofins_value,
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
    )

    cofins_st_cst_id = fields.Many2one(
        related="cofins_st_tax_id.cst_out_id",
        string="CST COFINS ST",
        readonly=True,
        required=True,
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
        store=True,
    )

    cofins_st_bc_value = fields.Float(
        string="Valor da Base de Calculo do COFINS ST", digits=(13, 2)
    )

    cofins_st_value = fields.Float(string="Valor do COFINS ST", digits=(13, 2))

    cofins_st_bc_quantity = fields.Float(
        string="Quantidade COFINS ST (Tributado por quantidade)", digits=(12, 4)
    )

    cofins_st_tax_quantity = fields.Float(
        string="Aliquota em reais COFINS ST (Tributado por quantidade)", digits=(11, 4)
    )

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

    # === Grupo UA. Tributos Devolvidos ===
    #  IPI Devolvido

    # Valor Total do IPI Devolvido.
    # enquanto o icms vai destacado na nota em caso de devolucao, o ipi nao e destacado
    # e vai nesse campo. Se destacar o ipi, vai gerar debito de ipi pra empresa.
    total_ipi_returned = fields.Float(
        string="Valor Total do IPI Devolvido", digits=(13, 2)
    )

    # Percentual da Mercadoria Devolvida
    total_product_returned_percentage = fields.Float(
        string="Percentual da Mercadoria Devolvida", digits=(3, 2)
    )
