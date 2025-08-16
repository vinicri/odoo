from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
import random


OPERATION_TYPE = [("0", "Entrada"), ("1", "Saída")]

DESTINATION_ID = [
    ("1", "Operação interna"),
    ("2", "Operação interestadual"),
    ("3", "Operação com exterior"),
]

DANFE_PRINT_FORMAT = [
    ("0", "Sem geração de DANFE"),
    ("1", "DANFE normal, Retrato"),
    ("2", "DANFE normal, Paisagem"),
    ("3", "DANFE Simplificado"),
    ("4", "DANFE NFC-e"),
    ("5", "DANFE NFC-e em mensagem eletrônica"),
]

EMISSION_TYPE = [
    ("1", "Emissão normal (não em contingência)"),
    ("2", "Contingência FS-IA"),
    ("3", "Contingência SCAN"),  # desativado
    ("4", "Contingência EPEC"),
    ("5", "Contingência FS-DA"),
    ("6", "Contingência SVC-AN"),
    ("7", "Contingência SVC-RS"),
    # Observação: Para a NFC-e somente é válida a opção de contingência: 9-Contingência Off-Line e, a critério da UF, opção 4-Contingência EPEC. (NT 2015/002)
    ("9", "Contingência off-line da NFC-e"),
]

PRESENCE_INDICATOR = [
    ("0", "Não se aplica (NF complementar ou de ajuste)"),
    ("1", "Operação presencial"),
    ("2", "Operação não presencial, pela Internet"),
    ("3", "Operação não presencial, Teleatendimento"),
    ("4", "NFC-e em operação com entrega a domicílio"),
    ("5", "Operação presencial, fora do estabelecimento"),
    ("9", "Operação não presencial, outros"),
]

EMISSION_FINALITY = [
    ("1", "NF-e normal"),
    ("2", "NF-e complementar"),
    ("3", "NF-e de ajuste"),
    # obrigatorio referenciar a nota de entrada ou saida
    # (se o proprio vendedor estiver emitindo a nota de entrada pra devolucao)
    ("4", "Devolução de mercadoria"),
]

FINAL_CUSTOMER_OPERATION = [
    ("0", "Normal (irá revender a mercadoria ou utilizar como insumo)"),
    ("1", "Consumidor final"),
]

INTERMEDIATOR_INDICATOR = [
    ("0", "Operação sem intermediador (em site ou plataforma própria)"),
    ("1", "Operação em site ou plataforma de terceiros (intermediadores/marketplace)"),
]


EMISSION_PROCESS = [
    ("0", "Emissão de NF-e com aplicativo do contribuinte"),
    ("1", "Emissão de NF-e avulsa pelo Fisco"),
    (
        "2",
        "Emissão de NF-e avulsa, pelo contribuinte com seu certificado digital, através do site do Fisco",
    ),
    ("3", "Emissão NF-e pelo contribuinte com aplicativo fornecido pelo Fisco"),
]

# Código de Regime Tributário.
CRT_SELECTION = [
    ("1", "Simples Nacional"),
    ("2", "Simples Nacional, excesso sublimite de receita bruta"),
    ("3", "Regime Normal"),
]

RECIPIENT_IE_INDICATOR = [
    ("1", "Contribuinte ICMS (informar IE)"),
    ("2", "Contribuinte isento de Inscrição no cadastro de Contribuintes"),
    ("9", "Não Contribuinte, que pode ou não possuir Inscrição Estadual"),
]

FREIGHT_MODALITY = [
    ("0", "0 - Contratação do Frete por conta do Remetente (CIF)"),
    ("1", "1 - Contratação do Frete por conta do Destinatário (FOB)"),
    ("2", "2 - Contratação do Frete por conta de Terceiros"),
    ("3", "3 - Transporte Próprio por conta do Remetente"),
    ("4", "4 - Transporte Próprio por conta do Destinatário"),
    ("9", "9 - Sem Ocorrência de Transporte"),
]


class NFeDocument(models.Model):
    _name = "nfe.document"
    _description = "Documento Fiscal Eletrônico (NF-e/NFC-e)"
    _rec_name = "nfe_number"  # Campo para representação amigável do registro

    company_id = fields.Many2one(
        comodel_name="res.company",
        string="Empresa",
        required=True,
        readonly=True,
        compute=lambda self: self.env.company.id,
    )

    # === Grupo A. Dados da Nota Fiscal eletrônica  ===
    # infNFe - Grupo que contém as informações da NF-e
    # NFe - TAG raiz da NF-e (implicitamente representa o documento inteiro)

    nfe_version = fields.Char(string="Versão do Leiaute", required=True, default="4.00")
    # Versão do leiaute. Obrigatório. Tamanho fixo '4.00' .

    # Identificador da TAG a ser assinada. Informar a Chave de Acesso precedida do literal 'NFe'.
    # O DV garante a integridade da chave.
    access_key = fields.Char(
        string="Chave de Acesso", size=44, copy=False, readonly=True, index=True
    )

    # === Grupo B. Identificação da Nota Fiscal eletrônica  ===
    # Código da UF do emitente do Documento Fiscal. Utilizar a Tabela do IBGE de código de unidades da federação (Seção 8.1 do MOC – Visão Geral, Tabela de UF, Município e País).
    issuer_id = fields.Many2one(
        comodel_name="res.partner",
        string="Emitente",
        required=True,
        domain="[('country_id.code', '=', 'BR')]",
    )

    issuer_state_id = fields.Many2one(
        comodel_name="res.country.state",
        string="Estado de Destino",
        compute="_compute_emitter_state_id",
        required=True,
    )

    @api.depends("issuer_id")
    def _compute_issuer_state_id(self):
        for record in self:
            record.issuer_state_id = record.issuer_id.state_id

    issuer_state_code = fields.Char(
        related="emitter_state_id.ibge_code",
        string="Código do Estado de Destino",
        readonly=True,
        store=True,
    )

    # Informar a natureza da operação de que decorrer a saída ou a entrada, tais como: venda, compra, transferência, devolução, importação, consignação, remessa (para fins de demonstração, de industrialização ou outra), conforme previsto na alínea 'i', inciso I, art. 19 do CONVÊNIO S/Nº, de 15 de dezembro de 1970.
    operation_nature_id = fields.Many2one(
        comodel_name="l10n_br_nfe.nfe.operation_nature",
        string="Natureza da Operação",
        required=True,
        size=60,
        help="Natureza da operação da NF-e",
    )

    # Código numérico que compõe a Chave de Acesso. Número aleatório gerado pelo emitente para cada NF-e para evitar acessos indevidos da NF-e. (v2.0)
    random_number = fields.Integer(
        string="Número Aleatório", size=8, compute="_compute_random_number"
    )

    def _compute_random_number(self):
        for record in self:
            record.random_number = random.randint(00000000, 99999999)

    # Série do Documento Fiscal. Preencher com zeros se a NF-e não possuir série.
    # Faixas de série 1-889 para Aplicativo do Contribuinte (CNPJ).
    # Faixas de série 920-969 para Aplicativo do Contribuinte (CPF).
    series_id = fields.Many2one(
        comodel_name="l10n_br_nfe.nfe.series",
        string="Série do Documento Fiscal",
        help="Série do Documento Fiscal",
        default=lambda self: self.env["l10n_br_nfe.nfe.series"].search(
            [
                ("document_model", "=", "55"),
                ("company_id", "=", self.env.company.id),
                ("is_default_for_document_model", "=", True),
            ],
            limit=1,
        ),
        required=True,
    )

    # Código do Modelo do Documento Fiscal. 55=NF-e (substitui modelo 1 ou 1A); 65=NFC-e (venda no varejo).
    document_model = fields.Selection(
        related="series_id.document_model",
        string="Modelo do Documento Fiscal",
        readonly=True,
        required=True,
        store=True,
    )

    # Número do Documento Fiscal. Faixa de 1 a 999999999
    nfe_number = fields.Integer(
        string="Número do Documento Fiscal",
        required=True,
        copy=False,
        readonly=True,
        compute="_compute_nfe_number",
    )

    def _compute_nfe_number(self):
        for record in self:
            record.nfe_number = record.series_id.next_seq_number()

    # Data e hora de emissão do Documento Fiscal. Formato UTC (Universal Coordinated Time): AAAA-MM-DDThh:mm:ssTZD.
    emission_datetime = fields.Datetime(
        string="Data e Hora de Emissão", required=True, default=fields.Datetime.now
    )

    # Data e hora de Saída ou Entrada da Mercadoria/Produto. Formato UTC. Não informar para NFC-e.
    departure_arrival_datetime = fields.Datetime(string="Data e Hora de Saída/Entrada")

    @api.onchange("document_model")
    def _onchange_series_id(self):
        if self.document_model == "65":
            self.departure_arrival_datetime = False

    # Tipo de Operação. 0=Entrada; 1=Saída.
    operation_type = fields.Selection(
        related="operation_nature_id.type",
        string="Tipo de Operação",
        required=True,
        readonly=True,
        store=True,
    )

    # Identificador de local de destino da operação. 1 = Operação interna; 2 = Operação interestadual; 3 = Operação com exterior
    destination_id = fields.Selection(
        DESTINATION_ID,
        string="Identificador de Local de Destino",
        required=True,
        readonly=True,
        compute="_compute_destination_id",
        store=True,
    )

    @api.depends("issuer_id", "recipient_id")
    def _compute_destination_id(self):
        for record in self:
            if record.issuer_id.state_id == record.recipient_id.state_id:
                record.destination_id = "1"
            elif record.issuer_id.country_id == record.recipient_id.country_id:
                record.destination_id = "2"
            else:
                record.destination_id = "3"

    city_id_fg = fields.Many2one(
        comodel_name="l10n_br_base.res.city",
        domain="[('state_id', '=', state_id),   ('ibge_code', '!=', False)]",
        string="Código Município de Ocorrência do Fato Gerador do ICMS",
        help="Código do Município de Ocorrência do Fato Gerador do ICMS. Usar Tabela IBGE.",
    )

    # Informar o município de ocorrência do fato gerador do ICMS. Utilizar a Tabela do IBGE (Seção 8.2 do MOC – Visão Geral, Tabela de UF, Município e País)
    city_code_fg = fields.Char(
        related="issuer_id.city_id.ibge_code",
        string="Código Município Fato Gerador",
        readonly=True,
        store=True,
        help="Código do Município de Ocorrência do Fato Gerador do ICMS. Usar Tabela IBGE.",
    )

    def _danfe_print_format_default(self):
        if self.document_model == "55":
            return "1"
        else:
            return "4"

    def _danfe_print_format_options(self):
        if self.document_model == "55":
            return [
                ("0", "Sem geração de DANFE"),
                ("1", "DANFE normal, Retrato"),
                ("2", "DANFE normal, Paisagem"),
                ("3", "DANFE Simplificado"),
            ]
        else:
            return [
                ("0", "Sem geração de DANFE"),
                ("4", "DANFE NFC-e"),
                ("5", "DANFE NFC-e em mensagem eletrônica"),
            ]

    # Formato de Impressão do DANFE.
    danfe_print_format = fields.Selection(
        lambda self: self._danfe_print_format_options(),
        string="Formato de Impressão do DANFE",
        required=True,
        default=_danfe_print_format_default,
    )

    # Tipo de Emissão da NF-e. Para NFC-e, somente 9 e 4 (a critério da UF) são válidas. [19, 20]
    emission_type = fields.Selection(
        EMISSION_TYPE, string="Tipo de Emissão da NF-e", required=True, default="1"
    )

    # Informar o Dígito Verificador da Chave de Acesso da NF-e, o DV será calculado com a aplicação do algoritmo módulo 11 (base 2,9) da Chave de Acesso. (vide item 5.4 do MOC – Visão Geral)
    access_key_dv = fields.Integer(
        string="Dígito Verificador Chave de Acesso",
        size=1,
        readonly=True,
        required=True,
        compute="_compute_access_key_dv",
    )

    def _compute_access_key_dv(self):
        for record in self:
            record.access_key_dv = 0

    # Informar o ambiente de emissão da NF-e. 0 = Produção; 1 = Homologação
    env_emission = fields.Selection(
        related="company_id.fiscal_document_emission_env",
        string="Ambiente de Emissão",
        required=True,
        readonly=True,
        store=True,
    )

    # Informar a finalidade da emissão da NF-e. 1 = NF-e normal; 2 = NF-e complementar; 3 = NF-e de ajuste; 4 = Devolução de mercadoria
    # obrigatorio referenciar a nota de entrada ou saida para devolucao
    emission_finality = fields.Selection(
        EMISSION_FINALITY, string="Finalidade da Emissão", required=True, default="1"
    )

    final_customer_operation = fields.Selection(
        FINAL_CUSTOMER_OPERATION,
        string="Operação com Consumidor final",
        required=True,
        default="1",
    )

    # Indicador de presença do comprador no estabelecimento comercial no momento da operação.
    presence_indicator = fields.Selection(
        PRESENCE_INDICATOR,
        string="Indicador de Presença do Comprador",
        required=True,
        default="1",
    )

    # Indicador de intermediador/marketplace. Criado na NT 2020.006.
    # (comentario adicionado por AI, verificar se é correto) Obrigatório se 'indIntermed' = 1, preencher 'infIntermed' (Grupo YB).
    intermediator_indicator = fields.Selection(
        INTERMEDIATOR_INDICATOR,
        string="Indicador de Intermediador/Marketplace",
        default="0",
    )

    # Processo de emissão da NF-e.
    emission_process = fields.Selection(
        EMISSION_PROCESS, string="Processo de Emissão da NF-e", required=True
    )

    # Informar a versão do aplicativo emissor de NF-e.
    app_version = fields.Char(
        string="Versão do Aplicativo Emissor", required=True, size=20, default="1.0.0"
    )

    # === Grupo BA. Documento Fiscal Referenciado ===
    # Referencia uma NF-e (modelo 55) emitida anteriormente, vinculada a NF-e atual, ou uma NFC-e (modelo 65)
    # se cliente devolver a mercadoria, faz uma nota de entrada referenciando a nota de saida
    # referencia documento fiscal emitido pela empresa
    ref_nfe_numbers = fields.Many2many(
        comodel_name="l10n_br_nfe.nfe_document",
        string="NFe e NFCe Referenciadas",
    )

    # todo referenciar notas fiscais de entrada, criar um novo campo

    # === Grupo C. Identificação do Emitente da Nota Fiscal eletrônica  ===
    # CNPJ do emitente
    issuer_cnpj = fields.Char(
        compute="_compute_issuer_cnpj",
        string="CNPJ do Emitente",
        store=True,
        size=14,
        readonly=True,
    )

    # CPF do emitente
    issuer_cpf = fields.Char(
        compute="_compute_issuer_cpf",
        string="CPF do Emitente",
        store=True,
        size=11,
        readonly=True,
    )

    @api.depends("issuer_id")
    def _compute_issuer_cnpj(self):
        for record in self:
            # check if its a cnpj or cpf
            if (
                record.issuer_id.company_type == "company"
                and len(record.issuer_id.vat) == 14
            ):
                record.issuer_cnpj = record.issuer_id.vat
            else:
                record.issuer_cnpj = False

    @api.depends("issuer_id")
    def _compute_issuer_cpf(self):
        for record in self:
            if (
                record.issuer_id.company_type == "person"
                and len(record.issuer_id.vat) == 11
            ):
                record.issuer_cpf = record.issuer_id.vat
            else:
                record.issuer_cpf = False

    # Razão social do emitente
    issuer_legal_name = fields.Char(
        related="issuer_id.legal_name",
        string="Razão Social",
        required=True,
        store=True,
        size=60,
        readonly=True,
    )

    # Nome fantasia do emitente
    issuer_trade_name = fields.Char(
        related="issuer_id.trade_name",
        string="Nome Fantasia",
        store=True,
        size=60,
        readonly=True,
    )

    # Logradouro do emitente.
    issuer_street = fields.Char(
        related="issuer_id.street",
        string="Logradouro",
        store=True,
        required=True,
        size=60,
    )

    # Número do endereço do emitente.
    issuer_street_number = fields.Char(
        related="issuer_id.street_number",
        string="Número",
        store=True,
        required=True,
        size=60,
    )

    # Complemento do endereço do emitente. Opcional.
    issuer_street_complement = fields.Char(
        related="issuer_id.street_complement",
        string="Complemento",
        store=True,
        size=60,
    )

    # Bairro do emitente.
    issuer_district = fields.Char(
        related="issuer_id.district",
        string="Bairro",
        store=True,
        required=True,
        size=60,
    )

    # Código do município do emitente. Usar Tabela IBGE.
    issuer_city_code = fields.Char(
        related="issuer_id.city_id.ibge_code",
        string="Código do Município",
        store=True,
        required=True,
        size=7,
    )

    # Nome do município do emitente.
    issuer_city_name = fields.Char(
        related="issuer_id.city_id.name",
        string="Município",
        store=True,
        required=True,
        size=60,
    )

    # Sigla da UF do emitente.
    issuer_state = fields.Char(
        related="issuer_id.state_id.code",
        string="UF",
        store=True,
        required=True,
        size=2,
    )

    # Código do CEP do emitente. Informar zeros não significativos.
    issuer_zip = fields.Char(
        related="issuer_id.unformatted_zip",
        string="CEP",
        store=True,
        required=True,
        size=8,
    )

    # Código do País do emitente. 1058=Brasil. Opcional.
    issuer_country_code = fields.Integer(
        string="Código País",
        store=True,
        size=4,
    )

    # Nome do País do emitente. Brasil ou BRASIL. Opcional.
    issuer_country_name = fields.Char(
        related="issuer_id.country_id.name",
        string="Nome País",
        store=True,
        size=60,
    )
    # Nome do País do emitente. Brasil ou BRASIL. Opcional.

    # Telefone do emitente. Preencher com DDD + número. Opcional.
    issuer_phone = fields.Char(
        related="issuer_id.phone", string="Telefone Emitente", store=True, size=14
    )

    # Inscrição Estadual do Emitente. Informar somente algarismos, sem formatação.
    issuer_ie = fields.Char(
        related="issuer_id.inscr_est",
        string="Inscrição Estadual Emitente",
        store=True,
        size=14,
    )

    # IE do Substituto Tributário da UF de destino da mercadoria. Opcional.
    # issuer_iest = fields.Char(string="IE Substituto Tributário Emitente", store=True, size=14)

    # Inscrição Municipal do Prestador de Serviço. Informado na emissão de NF-e conjugada. Opcional
    issuer_im = fields.Char(
        related="issuer_id.inscr_mun",
        string="Inscrição Municipal Emitente",
        store=True,
        size=15,
    )

    # CNAE fiscal. Opcional. Pode ser informado quando a Inscrição Municipal (C19) for informada.
    # issuer_cnae = fields.Char(related='issuer_id.cnae', string="CNAE Fiscal Emitente", store=True, size=7)

    # Código de Regime Tributário.
    issuer_crt = fields.Selection(
        CRT_SELECTION, string="Código de Regime Tributário", required=True
    )

    # === Grupo E. Identificação do Destinatário da NF-e  ===
    # Identificação do Destinatário da NF-e. Obrigatório para NF-e (modelo 55).

    recipient_id = fields.Many2one(
        comodel_name="res.partner",
        string="Destinatário",
        required=True,
    )

    # CNPJ do destinatário
    recipient_cnpj = fields.Char(
        compute="_compute_recipient_cnpj",
        string="CNPJ do Destinatário",
        store=True,
        size=14,
        readonly=True,
    )

    # CPF do destinatário
    recipient_cpf = fields.Char(
        compute="_compute_recipient_cpf",
        string="CPF do Destinatário",
        store=True,
        size=11,
        readonly=True,
    )

    # Identificação do destinatário no caso de comprador estrangeiro. Informar esta tag no caso de operação com o exterior
    recipient_foreign_id = fields.Char(
        compute="_compute_recipient_foreign_id",
        string="ID Estrangeiro Destinatário",
        store=True,
        size=20,
    )

    # Razão Social ou Nome do destinatário. Obrigatório para NF-e (modelo 55), opcional para NFC-e (modelo 65)
    recipient_name = fields.Char(
        related="recipient_id.legal_name",
        string="Razão Social/Nome Destinatário",
        store=True,
        size=60,
    )

    # Logradouro do destinatário.
    recipient_street = fields.Char(
        related="recipient_id.street",
        string="Logradouro Destinatário",
        store=True,
        size=60,
    )

    # Número do endereço do destinatário.
    recipient_street_number = fields.Char(
        related="recipient_id.street_number",
        string="Número Destinatário",
        store=True,
        size=60,
    )

    # Complemento do endereço do destinatário. Opcional.
    recipient_street_complement = fields.Char(
        related="recipient_id.street_complement",
        string="Complemento Destinatário",
        store=True,
        size=60,
    )

    # Bairro do destinatário.
    recipient_district = fields.Char(
        related="recipient_id.district",
        string="Bairro Destinatário",
        store=True,
        size=60,
    )

    # Código do município do destinatário. Usar Tabela IBGE.
    recipient_city_code = fields.Char(
        related="recipient_id.city_id.ibge_code",
        string="Código Município Destinatário",
        store=True,
        size=7,
    )

    # Nome do município do destinatário. Informar 'EXTERIOR' para operações com o exterior.
    recipient_city_name = fields.Char(
        related="recipient_id.city_id.name",
        string="Nome Município Destinatário",
        store=True,
        size=60,
    )

    # Sigla da UF do destinatário. Informar 'EX' para operações com o exterior.
    recipient_state = fields.Char(
        related="recipient_id.state_id.code",
        string="UF Destinatário",
        store=True,
        size=2,
    )

    # Código do CEP do destinatário. Informar zeros não significativos. Opcional.
    recipient_zip = fields.Char(
        related="recipient_id.zip", string="CEP Destinatário", store=True, size=8
    )

    # Código do País do destinatário. Usar Tabela BACEN. Opcional.
    recipient_country_code = fields.Integer(
        related="recipient_id.country_id.code",
        string="Código País Destinatário",
        store=True,
        size=4,
    )

    # Nome do País do destinatário. Opcional.
    recipient_country_name = fields.Char(
        related="recipient_id.country_id.name",
        string="Nome País Destinatário",
        store=True,
        size=60,
    )

    # Telefone do destinatário. Preencher com o Código DDD + número do telefone. Nas operações com exterior é permitido informar o código do país + código da localidade + número do telefone (v2.0)
    recipient_phone = fields.Char(
        related="recipient_id.phone",
        string="Telefone Destinatário",
        store=True,
        size=14,
    )

    # Indicador da IE do Destinatário. Para NFC-e ou operação com Exterior, informar 9 e não a tag IE.
    recipient_ie_indicator = fields.Selection(
        RECIPIENT_IE_INDICATOR, string="Indicador da IE do Destinatário", required=True
    )

    # Inscrição Estadual do Destinatário. Obrigatorio se o indicador da IE do Destinatário for 1
    recipient_ie = fields.Char(
        related="recipient_id.inscr_est",
        string="Inscrição Estadual Destinatário",
        store=True,
        size=14,
    )

    # Inscrição na SUFRAMA. Obrigatório em operações com incentivos fiscais SUFRAMA. Opcional.
    recipient_suframa = fields.Char(
        related="recipient_id.suframa",
        string="IE SUFRAMA Destinatário",
        store=True,
        size=9,
    )

    # Campo opcional, pode ser informado na NF-e conjugada, com itens de produtos sujeitos ao ICMS e itens de serviços sujeitos ao ISSQN.
    recipient_im = fields.Char(
        related="recipient_id.inscr_mun",
        string="Inscrição Municipal Destinatário",
        store=True,
        size=15,
    )

    # Campo para informar o e-mail de recepção da NF-e indicado pelo destinatário. Opcional.
    recipient_email = fields.Char(
        related="recipient_id.nfe_document_email",
        string="Email Destinatário",
        store=True,
        size=60,
    )

    # === Grupo GA. Autorização para obter XML  ===
    # autXML - Pessoas autorizadas a acessar o XML da NF-e
    authorized_xml_access_ids = fields.Many2many(
        comodel_name="res.partner",
        string="Pessoas Autorizadas a Acessar XML",
    )

    # === Grupo H. Detalhamento de Produtos e Serviços da NF-e  ===
    # det - Detalhamento de Produtos e Serviços. Múltiplas ocorrências (máximo = 990).

    invoice_line_ids = fields.One2many(
        "nfe.document.line", "nfe_id", string="Itens da Nota Fiscal", copy=True
    )

    # === Grupo W. Total da NF-e  ===
    # total - Totais da NF-e

    # Totais do ICMS

    # Base de Cálculo do ICMS.
    total_icms_base = fields.Float(string="BC do ICMS", digits=(13, 2))

    total_icms = fields.Float(string="Valor Total do ICMS", digits=(13, 2))
    # Valor Total do ICMS.

    total_icms_deson = fields.Float(string="Valor ICMS Desonerado", digits=(13, 2))
    # Valor Total do ICMS desonerado.

    # == icms difal ==

    total_fcp_uf_dest = fields.Float(
        string="Valor Total FCP da UF de Destino", digits=(13, 2)
    )
    # Valor Total do Fundo de Combate à Pobreza da UF de Destino.

    total_icms_uf_dest = fields.Float(
        string="Valor Total do ICMS da UF de Destino", digits=(13, 2)
    )
    # Valor Total do ICMS da UF de Destino.

    total_fcp = fields.Float(string="Valor Total FCP", digits=(13, 2))
    # Valor Total do Fundo de Combate à Pobreza.

    total_icms_st_base = fields.Float(
        string="Valor Total da Base de Calculo do ICMS ST", digits=(13, 2)
    )
    # Valor Total da Base de Calculo do ICMS ST.

    total_icms_st_value = fields.Float(string="Valor Total do ICMS ST", digits=(13, 2))
    # Valor Total do ICMS ST.

    total_icms_st_fcp = fields.Float(string="Valor Total FCP ST", digits=(13, 2))
    # Valor Total do FCP retido por Substituição Tributária.

    total_icms_fcp_st_reduction = fields.Float(
        string="Valor Total do FCP ST Retido Anteriormente por Substituição Tributária",
        digits=(13, 2),
    )
    # Valor Total do FCP ST Retido Anteriormente por Substituição Tributária.

    total_products = fields.Float(
        string="Valor Total dos Produtos e Serviços", required=True, digits=(13, 2)
    )
    # Valor Total dos Produtos e Serviços.

    total_freight = fields.Float(string="Valor Total do Frete", digits=(13, 2))
    # Valor Total do Frete.

    total_insurance = fields.Float(string="Valor Total do Seguro", digits=(13, 2))
    # Valor Total do Seguro.

    total_discount = fields.Float(string="Valor Total do Desconto", digits=(13, 2))
    # Valor Total do Desconto.

    total_ii = fields.Float(
        string="Valor Total do Imposto de Importação", digits=(13, 2)
    )
    # Valor Total do Imposto de Importação.

    total_ipi = fields.Float(string="Valor Total do IPI", digits=(13, 2))
    # Valor Total do IPI.

    total_ipi_returned = fields.Float(
        string="Valor Total do IPI Devolvido", digits=(13, 2)
    )
    # Valor Total do IPI Devolvido.

    total_pis = fields.Float(string="Valor Total do PIS", digits=(13, 2))
    # Valor Total do PIS.

    total_cofins = fields.Float(string="Valor Total da COFINS", digits=(13, 2))
    # Valor Total da COFINS.

    total_other_expenses = fields.Float(
        string="Outras Despesas Acessórias", digits=(13, 2)
    )
    # Outras Despesas acessórias.

    total_nfe = fields.Float(
        string="Valor Total da NF-e", required=True, digits=(13, 2)
    )
    # Valor Total da NF-e.

    total_approx_taxes = fields.Float(
        string="Valor Aproximado dos Tributos", digits=(13, 2)
    )
    # Total do valor aproximado dos tributos. Opcional. [227, 228]

    # == Grupo W02. Total da NF-e / Retenção de Tributos ==
    # Valor Total do PIS Retido.
    pis_retention = fields.Float(string="Valor Total do PIS Retido", digits=(13, 2))

    # Valor Total da COFINS Retida.
    cofins_retention = fields.Float(
        string="Valor Total da COFINS Retida", digits=(13, 2)
    )

    # Valor Total do CSLL Retido.
    csll_retention = fields.Float(string="Valor Total do CSLL Retido", digits=(13, 2))

    # Valor Total do ICMS Retido.
    icms_retention = fields.Float(string="Valor Total do ICMS Retido", digits=(13, 2))

    # Valor Total da Base de Calculo do IRRF.
    irrf_base = fields.Float(
        string="Valor Total da Base de Calculo do IRRF", digits=(13, 2)
    )

    # Valor Total do IRRF Retido.
    irrf_retention = fields.Float(string="Valor Total do IRRF Retido", digits=(13, 2))

    # Valor Total da Base de Calculo do INSS.
    inss_base = fields.Float(
        string="Base de Cálculo da Retenção da Previdência Social", digits=(13, 2)
    )

    # Valor Total da Previdência Social Retida.
    inss_retention = fields.Float(
        string="Valor Total da Previdência Social Retida", digits=(13, 2)
    )

    # Modalidade de Frete.
    freight_modality = fields.Selection(
        string="Modalidade de Frete",
        selection=FREIGHT_MODALITY,
    )

    # === Grupo Y. Dados da Cobrança  ===
    #  Dados da Fatura

    # Número da Fatura. Opcional.
    billing_number = fields.Char(string="Número da Fatura", size=60)

    # Valor Original da Fatura.
    billing_original_value = fields.Float(
        string="Valor Original da Fatura", digits=(13, 2)
    )

    # Valor do Desconto da Fatura.
    billing_discount_value = fields.Float(
        string="Valor do Desconto da Fatura", digits=(13, 2)
    )

    # Valor Líquido da Fatura.
    billing_liquid_value = fields.Float(
        string="Valor Líquido da Fatura", digits=(13, 2)
    )

    billing_installment_ids = fields.One2many(
        "l10n_br_nfe.nfe.document.installment",
        "nfe_id",
        string="Parcelas da Fatura",
        copy=True,
    )

    # Grupo YB. Informações do Intermediador da Transação
    # marketplace_cnpj = fields.Many2one(
    #     'res.partner',
    #     string="Marketplace",
    #     #domain is marketplace
    # )

    # Nome do usuário ou identificação do perfil do vendedor no site do intermediador (agenciador, plataforma de delivery, marketplace e similar) de serviços e de negócios.
    # marketplace_username = fields.Char(string="Identificação do Vendedor no Marketplace", size=60)

    # === Grupo YA. Informações de Pagamento  ===
    # pag - Grupo de Informações de Pagamento. Obrigatório.

    payment_detail_ids = fields.One2many(
        "l10n_br_nfe.nfe.document.payment.detail",
        "nfe_id",
        string="Detalhes do Pagamento",
    )

    # Grupo Z. Informações Adicionais da NF-e
    # Deverá informar a base legal do benefício fiscal utilizado nos dados
    # adicionais + Art. 9º do Convênio ICMS S/N de 1970
    #  Empresa do Simples Nacional em todas as notas fiscais:
    # "DOCUMENTO EMITIDO POR ME OU EPP OPTANTE PELO SIMPLES NACIONAL";
    # e "NÃO GERA DIREITO A CREDITO FISCAL DE IPI". \

    # remessa pra demonstracao - tem que ter retorno
    #     A NF será emitida contra a pessoa que irá receber a
    # mercadoria
    # • Natureza da operação: Remessa para Demonstração
    # • CFOP: 5.912 ou 6.912
    # • CST ICMS: 50 - ICMS Suspenso
    # • No dados adicionais:
    # "Mercadoria
    # remetida para
    # demonstração" e "Imposto suspenso nos termos do Ajuste
    # SINIEF 02/18"

    # doacao, bonificacao, amostra gratis simples CSOSN 400 - nao tributada
    # CFOP 5.910/6.910 - Remessa em bonificação, doação ou brinde
    # Para Simples Nacional: CSOSN 400 - Não tributado
    # Demais regimes: Tributa normal conforme mercadoria, inclusive DIFA ou
    # ICMS ST. Para bonificação ver se a UF concede dispensa

    # Para as operações que permita o crédito de ICMS, será acrescentada a seguinte expressão:
    # • "PERMITE O APROVEITAMENTO DO CRÉDITO DE ICMS NO VALOR DE R$ ...;
    # CORRESPONDENTE À ALÍQUOTA DE .%, NOS TERMOS DO ART. 23, DA LC 123/2006".
    additional_information = fields.Text(string="Informações Adicionais", size=2000)

    # Grupo ZD. Informações do Responsável Técnico (NT 2018.005)

    qr_code = fields.Text(string="QR Code", size=600)

    # signature = fields.Binary(string="Assinatura Digital", attachment=True)

    # === Outros Campos e Métodos ===

    state = fields.Selection(
        [
            ("draft", "Rascunho"),
            ("done", "Validado"),
            ("cancel", "Cancelado"),
            ("denied", "Denegado"),
        ],
        string="Status da NF-e",
        default="draft",
        copy=False,
    )
    # Status de controle interno do documento na Odoo.

    @api.depends("recipient_id")
    def _compute_recipient_cnpj(self):
        for record in self:
            if len(record.recipient_id.vat) == 14:
                record.recipient_cnpj = record.recipient_id.vat
            else:
                record.recipient_cnpj = False

    @api.depends("recipient_id")
    def _compute_recipient_cpf(self):
        for record in self:
            if len(record.recipient_id.vat) == 11:
                record.recipient_cpf = record.recipient_id.vat
            else:
                record.recipient_cpf = False

    # Identificação do destinatário no caso de comprador estrangeiro. Informar esta tag no caso de operação com o exterior
    @api.depends("recipient_id")
    def _compute_recipient_foreign_id(self):
        for record in self:
            if record.recipient_id.is_foreign:
                record.recipient_foreign_id = record.recipient_id.vat
            else:
                record.recipient_foreign_id = False

    @api.constrains("series", "nfe_number", "emission_type")
    def _check_unique_nfe_natural_key(self):
        # Validação da Chave Natural (UF, CNPJ/CPF do Emitente, Série, Número, Modelo, Ambiente de Autorização/Tipo de Emissão)
        # O Sistema de Autorização de Uso da SEFAZ rejeita pedidos de autorização duplicados de Chave Natural.
        for record in self:
            domain = [
                ("document_model", "=", record.document_model),
                (
                    "cnpj_cpf_emit",
                    "=",
                    record.cnpj_cpf_emit,
                ),  # Assumindo que o CNPJ/CPF do emitente é um identificador chave para a unicidade
                ("series", "=", record.series),
                ("nfe_number", "=", record.nfe_number),
                ("emission_type", "=", record.emission_type),
                ("id", "!=", record.id),
            ]
            if self.search(domain):
                raise ValidationError(
                    _(
                        "A Chave Natural (Modelo, CNPJ/CPF Emitente, Série, Número, Tipo de Emissão) já existe para outra NF-e."
                    )
                )

    @api.constrains("access_key")
    def _check_access_key_format(self):
        # A Chave de Acesso de identificação da Nota Fiscal eletrônica é um conjunto de 44 caracteres numéricos.
        for record in self:
            if record.access_key and (
                not record.access_key.isdigit() or len(record.access_key) != 44
            ):
                raise ValidationError(
                    _("A Chave de Acesso deve conter 44 dígitos numéricos.")
                )

    @api.constrains("cnpj_cpf_emit", "recipient_cnpj_cpf")
    def _check_cnpj_cpf_format(self):
        # CNPJ com zeros, nulo ou DV inválido
        # CPF com zeros, nulo, 111..., 222..., ..., ou DV inválido
        for record in self:
            if record.cnpj_cpf_emit and not (
                len(record.cnpj_cpf_emit) == 14 and record.cnpj_cpf_emit.isdigit()
            ):
                raise ValidationError(
                    _(
                        "O CNPJ/CPF do Emitente deve ter 14 dígitos numéricos para CNPJ ou 11 para CPF."
                    )
                )
            if record.recipient_cnpj_cpf and not (
                len(record.recipient_cnpj_cpf) == 14
                and record.recipient_cnpj_cpf.isdigit()
            ):
                raise ValidationError(
                    _(
                        "O CNPJ/CPF do Destinatário deve ter 14 dígitos numéricos para CNPJ ou 11 para CPF."
                    )
                )

    @api.constrains("danfe_print_format", "emission_type")
    def _check_danfe_contingency_nfc_e(self):
        # NFC-e (modelo 65) não permite emissão em contingência usando EPEC ou formulário de segurança (tpEmis != 4, 5)
        # Para NFC-e (modelo 65) tpEmis só pode ser 9 (Contingência Off-Line) ou, a critério da UF, 4 (Contingência EPEC).
        for record in self:
            if record.document_model == "65":  # NFC-e
                if record.emission_type not in [
                    "1",
                    "9",
                    "4",
                ]:  # Normal, Off-line, EPEC
                    raise ValidationError(
                        _(
                            "Tipo de Emissão inválido para NFC-e. Apenas Normal (1), Contingência Off-Line (9) e EPEC (4) são permitidos."
                        )
                    )
                if (
                    record.danfe_print_format in ["1", "2", "3"]
                    and record.emission_type != "1"
                ):
                    raise ValidationError(
                        _(
                            "DANFE normal/simplificado só pode ser gerado para NFC-e em emissão normal."
                        )
                    )

    @api.constrains("emission_type")
    def _check_contingency_justification(self):
        # Se emissão normal (tpEmis = 1-Normal): dhCont e xJust não devem ser informados.
        # Se emissão em contingência utilizando DPEC, formulário de segurança ou contingência off-line (tpEmis = 2, 4, 5 ou 9):
        # dhCont e xJust devem ser informados.
        # Nota: dhCont e xJust não são campos no modelo Odoo simplificado, mas seriam validados se presentes.
        pass
