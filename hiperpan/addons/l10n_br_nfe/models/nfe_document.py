from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
from .utils import is_valid_phone
import random
import pytz

# from ..utils import nfe as nfe_utils
import lxml.etree as etree


def convert_datetime_to_company_tz(dt_utc, company):
    """
    Converte um datetime UTC para o timezone da empresa.

    Args:
        dt_utc: datetime object (pode ser naive ou aware em UTC)

    Returns:
        datetime object no timezone da empresa
    """

    if not dt_utc:
        return None

    # Garante que o datetime está em UTC
    if dt_utc.tzinfo is None:
        utc_dt = pytz.UTC.localize(dt_utc)
    else:
        utc_dt = dt_utc.astimezone(pytz.UTC)

    # Converte para o timezone da empresa
    company_tz = pytz.timezone(company.time_zone)
    return utc_dt.astimezone(company_tz)


def format_datetime_for_nfe(dt_field, company):
    """
    Formata um datetime para o padrão NFe: AAAA-MM-DDThh:mm:ssTZD

    Args:
        dt_field: datetime do Odoo (em UTC)

    Returns:
        String formatada no padrão ISO 8601 com timezone
        Exemplo: '2025-04-04T06:22:00-03:00'
    """
    if not dt_field:
        return None

    # Converte para o timezone da empresa
    local_dt = convert_datetime_to_company_tz(dt_field, company)

    # Formata no padrão ISO 8601
    return local_dt.isoformat()


def buildNfeXmlFromNfeDocumentModel(nfe_document):
    root = etree.Element("nfe")

    # grupo A
    infNfe = etree.SubElement(root, "infNfe")
    infNfe.set("versao", nfe_document.nfe_version)
    infNfe.set("Id", nfe_document.access_key)

    # grupo B
    ide = etree.SubElement(infNfe, "ide")
    cUF = etree.SubElement(ide, "cUF")
    cUF.text = nfe_document.issuer_state_code

    cNF = etree.SubElement(ide, "cNF")
    cNF.text = nfe_document.random_number

    natOp = etree.SubElement(ide, "natOp")
    natOp.text = nfe_document.operation_nature_name

    mod = etree.SubElement(ide, "mod")
    mod.text = nfe_document.document_model

    serie = etree.SubElement(ide, "serie")
    serie.text = str(nfe_document.nfe_series)

    nNF = etree.SubElement(ide, "nNF")
    nNF.text = str(nfe_document.nfe_number)

    dhEmi = etree.SubElement(ide, "dhEmi")
    dhEmi.text = format_datetime_for_nfe(
        nfe_document.issue_datetime, nfe_document.company_id
    )

    if nfe_document.document_model == "55":
        # nao se deve informar para NFC-e
        dhSaiEnt = etree.SubElement(ide, "dhSaiEnt")
        dhSaiEnt.text = format_datetime_for_nfe(
            nfe_document.departure_arrival_datetime, nfe_document.company_id
        )

    tpNF = etree.SubElement(ide, "tpNF")
    tpNF.text = nfe_document.operation_type

    idDest = etree.SubElement(ide, "idDest")
    idDest.text = nfe_document.destination_id

    cMunFG = etree.SubElement(ide, "cMunFG")
    cMunFG.text = nfe_document.city_code_fg

    tpImp = etree.SubElement(ide, "tpImp")
    tpImp.text = nfe_document.danfe_print_format

    tpEmis = etree.SubElement(ide, "tpEmis")
    tpEmis.text = nfe_document.emission_type

    cDV = etree.SubElement(ide, "cDV")
    cDV.text = nfe_document.access_key[-1]

    tpAmb = etree.SubElement(ide, "tpAmb")
    tpAmb.text = nfe_document.env_emission

    finNFe = etree.SubElement(ide, "finNFe")
    finNFe.text = nfe_document.emission_finality

    indFinal = etree.SubElement(ide, "indFinal")
    indFinal.text = nfe_document.final_customer_operation

    indPres = etree.SubElement(ide, "indPres")
    indPres.text = nfe_document.presence_indicator

    if nfe_document.intermediator_indicator:
        indIntermed = etree.SubElement(ide, "indIntermed")
        indIntermed.text = nfe_document.intermediator_indicator

    procEmi = etree.SubElement(ide, "procEmi")
    procEmi.text = nfe_document.emission_process

    verProc = etree.SubElement(ide, "verProc")
    verProc.text = nfe_document.app_version

    if nfe_document.emission_finality != "1":
        # grupo BA - Documento Fiscal Referenciado
        NFref = etree.SubElement(ide, "NFref")

        for ref_nfe_number in nfe_document.ref_nfe_numbers:
            refNFe = etree.SubElement(NFref, "refNFe")
            refNFe.text = ref_nfe_number.access_key

    # emitente
    emit = etree.SubElement(root, "emit")

    if nfe_document.issuer_id.company_type == "company":
        CNPJ = etree.SubElement(emit, "CNPJ")
        CNPJ.text = nfe_document.issuer_cnpj
    else:
        CPF = etree.SubElement(emit, "CPF")
        CPF.text = nfe_document.issuer_cpf

    xNome = etree.SubElement(emit, "xNome")
    xNome.text = nfe_document.issuer_legal_name

    xFant = etree.SubElement(emit, "xFant")
    xFant.text = nfe_document.issuer_trade_name

    enderEmit = etree.SubElement(emit, "enderEmit")
    xLgr = etree.SubElement(enderEmit, "xLgr")
    xLgr.text = nfe_document.issuer_street

    nro = etree.SubElement(enderEmit, "nro")
    nro.text = nfe_document.issuer_street_number

    if nfe_document.issuer_street_complement:
        xCpl = etree.SubElement(enderEmit, "xCpl")
        xCpl.text = nfe_document.issuer_street_complement

    xBairro = etree.SubElement(enderEmit, "xBairro")
    xBairro.text = nfe_document.issuer_district

    cMun = etree.SubElement(enderEmit, "cMun")
    cMun.text = nfe_document.issuer_city_code

    xMun = etree.SubElement(enderEmit, "xMun")
    xMun.text = nfe_document.issuer_city_name

    UF = etree.SubElement(enderEmit, "UF")
    UF.text = nfe_document.issuer_state

    CEP = etree.SubElement(enderEmit, "CEP")
    CEP.text = nfe_document.issuer_zip

    # opicional para o Brasil
    #  cPais = etree.SubElement(enderEmit, "cPais")
    # cPais.text = nfe_document.issuer_country_code

    # xPais = etree.SubElement(enderEmit, "xPais")
    # xPais.text = nfe_document.issuer_country_name

    fone = etree.SubElement(enderEmit, "fone")
    fone.text = nfe_document.issuer_phone

    IE = etree.SubElement(emit, "IE")
    IE.text = nfe_document.issuer_ie

    CRT = etree.SubElement(emit, "CRT")
    CRT.text = nfe_document.issuer_fiscal_framework

    if nfe_document.recipient_id:
        # Grupo E - Destinatário
        dest = etree.SubElement(root, "dest")

        if nfe_document.recipient_id.is_foreign:
            idEstrangeiro = etree.SubElement(dest, "idEstrangeiro")
            idEstrangeiro.text = nfe_document.recipient_foreign_id
        elif nfe_document.recipient_id.company_type == "company":
            dCNPJ = etree.SubElement(dest, "CNPJ")
            dCNPJ.text = nfe_document.recipient_cnpj
        else:
            dCPF = etree.SubElement(dest, "CPF")
            dCPF.text = nfe_document.recipient_cpf

        dXNome = etree.SubElement(dest, "xNome")
        dXNome.text = nfe_document.recipient_legal_name

        dEnderDest = etree.SubElement(dest, "enderDest")

        dXlgr = etree.SubElement(dEnderDest, "xLgr")
        dXlgr.text = nfe_document.recipient_street

        dNro = etree.SubElement(dEnderDest, "nro")
        dNro.text = nfe_document.recipient_street_number

        dXCpl = etree.SubElement(dEnderDest, "xCpl")
        dXCpl.text = nfe_document.recipient_street_complement

        dXBairro = etree.SubElement(dEnderDest, "xBairro")
        dXBairro.text = nfe_document.recipient_district

        dCMun = etree.SubElement(dEnderDest, "cMun")
        dCMun.text = nfe_document.recipient_city_code

        dXMun = etree.SubElement(dEnderDest, "xMun")
        dXMun.text = nfe_document.recipient_city_name

        dUF = etree.SubElement(dEnderDest, "UF")
        dUF.text = nfe_document.recipient_state

        dCEP = etree.SubElement(dEnderDest, "CEP")
        dCEP.text = nfe_document.recipient_zip

        if nfe_document.recipient_id.is_foreign:
            dCEP = etree.SubElement(dEnderDest, "CEP")
            dCEP.text = nfe_document.recipient_zip

        # dCPais = etree.SubElement(dEnderDest, "cPais")
        # dCPais.text = nfe_document.recipient_country_code

        # dXpais = etree.SubElement(dEnderDest, "xPais")
        # dXpais.text = nfe_document.recipient_country_name

        if nfe_document.recipient_phone:
            dFone = etree.SubElement(dEnderDest, "fone")
            dFone.text = nfe_document.recipient_phone

        indIEDest = etree.SubElement(dest, "indIEDest")
        indIEDest.text = nfe_document.recipient_ie_indicator

        if nfe_document.recipient_ie_indicator == "1":
            dIE = etree.SubElement(dest, "IE")
            dIE.text = nfe_document.recipient_ie

        if nfe_document.recipient_suframa:
            dSuframa = etree.SubElement(dest, "Suframa")
            dSuframa.text = nfe_document.recipient_suframa

        if nfe_document.recipient_email:
            dEmail = etree.SubElement(dest, "email")
            dEmail.text = nfe_document.recipient_email

    return root


def printNfeXml(nfe_document):
    root = buildNfeXmlFromNfeDocumentModel(nfe_document)
    print(etree.tostring(root, pretty_print=True).decode("utf-8"))


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

NFE_VERSION = [
    ("4.00", "4.00"),
]


class NFeDocument(models.Model):
    _name = "l10n_br_nfe.nfe.document"
    _description = "Documento Fiscal Eletrônico (NF-e/NFC-e)"
    _rec_name = "nfe_number"  # Campo para representação amigável do registro

    company_id = fields.Many2one(
        comodel_name="res.company",
        string="Empresa",
        required=True,
        readonly=True,
        default=lambda self: self.env.company.id,
    )

    # === Grupo A. Dados da Nota Fiscal eletrônica  ===
    # infNFe - Grupo que contém as informações da NF-e
    # NFe - TAG raiz da NF-e (implicitamente representa o documento inteiro)

    nfe_version = fields.Selection(
        NFE_VERSION, string="Versão do Leiaute", required=True, default="4.00"
    )
    # Versão do leiaute. Obrigatório. Tamanho fixo '4.00' .

    # Identificador da TAG a ser assinada. Informar a Chave de Acesso precedida do literal 'NFe'.
    # O DV garante a integridade da chave.
    access_key = fields.Char(
        string="Chave de Acesso",
        size=47,
        copy=False,
        readonly=True,
        index=True,
    )

    # === Grupo B. Identificação da Nota Fiscal eletrônica  ===
    # Código da UF do emitente do Documento Fiscal. Utilizar a Tabela do IBGE de código de unidades da federação (Seção 8.1 do MOC – Visão Geral, Tabela de UF, Município e País).
    issuer_id = fields.Many2one(
        comodel_name="res.partner",
        string="Emitente",
        required=True,
        default=lambda self: self.env.company.partner_id,
        domain="[('country_id.code', '=', 'BR')]",
    )

    # issuer_state_id = fields.Many2one(
    #     related="issuer_id.state_id",
    #     string="Estado de Destino",
    #     store=True,
    #     required=True,
    # )

    issuer_state_code = fields.Char(
        related="issuer_id.state_id.ibge_code",
        string="Código do Estado de Destino",
        readonly=True,
        store=True,
    )

    # Informar a natureza da operação de que decorrer a saída ou a entrada, tais como: venda, compra, transferência, devolução, importação, consignação, remessa (para fins de demonstração, de industrialização ou outra), conforme previsto na alínea 'i', inciso I, art. 19 do CONVÊNIO S/Nº, de 15 de dezembro de 1970.
    operation_nature_id = fields.Many2one(
        comodel_name="l10n_br_nfe.nfe.operation_nature",
        string="Natureza da Operação",
        required=True,
        help="Natureza da operação da NF-e",
    )

    operation_nature_name = fields.Char(
        related="operation_nature_id.name",
        string="Natureza da Operação",
        readonly=True,
        store=True,
    )

    # Tipo de Operação. 0=Entrada; 1=Saída.
    operation_type = fields.Selection(
        related="operation_nature_id.type",
        string="Tipo de Operação",
        store=True,
    )
    # Código numérico que compõe a Chave de Acesso. Número aleatório gerado pelo emitente para cada NF-e para evitar acessos indevidos da NF-e. (v2.0)
    random_number = fields.Char(
        string="Número Aleatório", size=8, compute="_compute_random_number"
    )

    def _compute_random_number(self):
        for record in self:
            random_number = random.randint(00000000, 99999999)
            record.random_number = str(random_number).zfill(8)

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
        domain="[('operation_type', '=', operation_type), ('active', '=', True), ('company_id', '=', company_id)]",
        required=True,
    )

    # Código do Modelo do Documento Fiscal. 55=NF-e (substitui modelo 1 ou 1A); 65=NFC-e (venda no varejo).
    document_model = fields.Selection(
        related="series_id.document_model",
        string="Modelo do Documento Fiscal",
        store=True,
    )

    nfe_series = fields.Integer(
        related="series_id.series",
        string="Série do Documento Fiscal",
        store=True,
    )

    # Número do Documento Fiscal. Faixa de 1 a 999999999
    nfe_number = fields.Integer(
        string="Número do Documento Fiscal",
        required=True,
        copy=False,
        readonly=True,
        store=True,
    )

    # Data e hora de emissão do Documento Fiscal. Formato UTC (Universal Coordinated Time): AAAA-MM-DDThh:mm:ssTZD.
    issue_datetime = fields.Datetime(
        string="Data e Hora de Emissão", required=True, default=fields.Datetime.now
    )

    # Data e hora de Saída ou Entrada da Mercadoria/Produto. Formato UTC. Não informar para NFC-e.
    departure_arrival_datetime = fields.Datetime(
        string="Data e Hora de Saída/Entrada",
        readonly=False,
        compute="_compute_departure_arrival_datetime",
    )

    @api.depends("issue_datetime")
    def _compute_departure_arrival_datetime(self):
        for record in self:
            if not record.departure_arrival_datetime:
                record.departure_arrival_datetime = record.issue_datetime

    # Identificador de local de destino da operação. 1 = Operação interna; 2 = Operação interestadual; 3 = Operação com exterior
    destination_id = fields.Selection(
        DESTINATION_ID,
        string="Identificador de Local de Destino",
        # required=True,
        readonly=True,
        compute="_compute_destination_id",
        store=True,
    )

    @api.depends(
        "issuer_id",
        "recipient_id",
        "issuer_id.state_id",
        "recipient_id.state_id",
        "issuer_id.country_id",
        "recipient_id.country_id",
    )
    def _compute_destination_id(self):
        for record in self:
            if record.issuer_id.state_id == record.recipient_id.state_id:
                record.destination_id = "1"
            elif record.issuer_id.country_id == record.recipient_id.country_id:
                record.destination_id = "2"
            else:
                record.destination_id = "3"

    # Informar o município de ocorrência do fato gerador do ICMS. Utilizar a Tabela do IBGE (Seção 8.2 do MOC – Visão Geral, Tabela de UF, Município e País)
    city_code_fg = fields.Char(
        related="issuer_id.city_id.ibge_code",
        string="Código Município Fato Gerador",
        readonly=True,
        store=True,
        help="Código do Município de Ocorrência do Fato Gerador do ICMS. Usar Tabela IBGE.",
    )

    # Formato de Impressão do DANFE.
    danfe_print_format = fields.Selection(
        DANFE_PRINT_FORMAT,
        string="Formato de Impressão do DANFE",
        required=True,
        # default=_danfe_print_format_default,
    )

    @api.onchange("document_model")
    def _onchange_document_model_danfe(self):
        for record in self:
            # Reset danfe_print_format to valid default when document_model changes"""
            if record.document_model == "55":
                # For NF-e, valid options are 0, 1, 2, 3
                if record.danfe_print_format not in ["0", "1", "2", "3"]:
                    record.danfe_print_format = "1"
            elif record.document_model == "65":
                # For NFC-e, valid options are 0, 4, 5
                if record.danfe_print_format not in ["0", "4", "5"]:
                    record.danfe_print_format = "4"

    @api.constrains("danfe_print_format")
    def _check_danfe_print_format(self):
        for record in self:
            if record.document_model == "55" and record.danfe_print_format not in [
                "0",
                "1",
                "2",
                "3",
            ]:
                raise ValidationError(
                    _("O Formato de Impressão do DANFE é inválido para NF-e.")
                )
            elif record.document_model == "65" and record.danfe_print_format not in [
                "0",
                "4",
                "5",
            ]:
                raise ValidationError(
                    _("O Formato de Impressão do DANFE é inválido para NFC-e.")
                )

    # Tipo de Emissão da NF-e. Para NFC-e, somente 9 e 4 (a critério da UF) são válidas. [19, 20]
    emission_type = fields.Selection(
        EMISSION_TYPE, string="Tipo de Emissão da NF-e", required=True, default="1"
    )

    # Informar o ambiente de emissão da NF-e. 0 = Produção; 1 = Homologação
    env_emission = fields.Selection(
        related="company_id.fiscal_document_emission_env",
        string="Ambiente de Emissão",
        # required=True,
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
    )

    @api.constrains("intermediator_indicator")
    def _check_intermediator_indicator(self):
        for record in self:
            if (
                record.presence_indicator in ["2", "3"]
                and not record.intermediator_indicator
            ):
                raise ValidationError(
                    _("O Indicador de Intermediador/Marketplace é obrigatório.")
                )
            if (
                record.presence_indicator in ["0", "1", "4", "5", "9"]
                and record.intermediator_indicator
            ):
                raise ValidationError(
                    _("O Indicador de Intermediador/Marketplace é inválido.")
                )

    # Processo de emissão da NF-e.
    emission_process = fields.Selection(
        EMISSION_PROCESS,
        string="Processo de Emissão da NF-e",
        required=True,
        default="0",
    )

    # Informar a versão do aplicativo emissor de NF-e.
    app_version = fields.Char(
        string="Versão do Aplicativo Emissor",
        required=True,
        size=20,
        default="1.0.0",
        readonly=True,
    )

    # === Grupo BA. Documento Fiscal Referenciado ===
    # Referencia uma NF-e (modelo 55) emitida anteriormente, vinculada a NF-e atual, ou uma NFC-e (modelo 65)
    # se cliente devolver a mercadoria, faz uma nota de entrada referenciando a nota de saida
    # referencia documento fiscal emitido pela empresa
    ref_nfe_numbers = fields.Many2many(
        comodel_name="l10n_br_nfe.nfe.document",
        string="NFe e NFCe Referenciadas",
        relation="nfe_document_ref_nfe_numbers_rel",
        column1="nfe_id",
        column2="ref_nfe_id",
        domain="[('id', '!=', id)]",
    )

    @api.constrains("ref_nfe_numbers", "emission_finality")
    def _check_ref_nfe_numbers(self):
        for record in self:
            if (
                record.emission_finality in ["2", "3", "4"]
                and not record.ref_nfe_numbers
            ):  # para devolucao de mercadoria, nao precisa referenciar
                raise ValidationError(
                    _(
                        "A NF-e complementar, de ajuste ou devolução de mercadoria deve referenciar ao menos uma NF-e ou NFC-e."
                    )
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

    @api.depends("issuer_id", "issuer_id.company_type", "issuer_id.vat")
    def _compute_issuer_cnpj(self):
        for record in self:
            if (
                record.issuer_id.company_type == "company"
                and record.issuer_id.vat
                and len(record.issuer_id.vat) == 14
            ):
                record.issuer_cnpj = record.issuer_id.vat
            else:
                record.issuer_cnpj = False

    @api.constrains("issuer_cnpj")
    def _check_issuer_cnpj(self):
        for record in self:
            if record.issuer_id.company_type == "company" and not record.issuer_cnpj:
                raise ValidationError(_("O CNPJ do Emitente é obrigatório."))
            if record.issuer_cnpj and not (len(record.issuer_cnpj) == 14):
                raise ValidationError(_("O CNPJ do Emitente deve ter 14 caracteres."))

    # CPF do emitente
    issuer_cpf = fields.Char(
        compute="_compute_issuer_cpf",
        string="CPF do Emitente",
        store=True,
        size=11,
        readonly=True,
    )

    @api.depends("issuer_id", "issuer_id.company_type", "issuer_id.vat")
    def _compute_issuer_cpf(self):
        for record in self:
            if (
                record.issuer_id.company_type == "person"
                and record.issuer_id.vat
                and len(record.issuer_id.vat) == 11
            ):
                record.issuer_cpf = record.issuer_id.vat
            else:
                record.issuer_cpf = False

    @api.constrains("issuer_cpf")
    def _check_issuer_cpf(self):
        for record in self:
            if record.issuer_id.company_type == "person" and not record.issuer_cpf:
                raise ValidationError(_("O CPF do Emitente é obrigatório."))
            if record.issuer_cpf and not (
                len(record.issuer_cpf) == 11 and record.issuer_cpf.isdigit()
            ):
                raise ValidationError(
                    _("O CPF do Emitente deve ter 11 dígitos numéricos.")
                )

    # Razão social do emitente
    issuer_legal_name = fields.Char(
        related="issuer_id.legal_name",
        string="Razão Social",
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
        size=60,
    )

    # Número do endereço do emitente.
    issuer_street_number = fields.Char(
        related="issuer_id.street_number",
        string="Número",
        store=True,
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
        size=60,
    )

    # Código do município do emitente. Usar Tabela IBGE.
    issuer_city_code = fields.Char(
        related="issuer_id.city_id.ibge_code",
        string="Código do Município",
        store=True,
        size=7,
    )

    # Nome do município do emitente.
    issuer_city_name = fields.Char(
        string="Município",
        store=True,
        size=60,
        compute="_compute_issuer_city_name",
    )

    @api.depends("issuer_id", "issuer_id.city_id")
    def _compute_issuer_city_name(self):
        for record in self:
            if record.issuer_id.city_id:
                record.issuer_city_name = record.issuer_id.city_id.with_context(
                    lang="pt_BR"
                ).name
            else:
                record.issuer_city_name = False

    @api.constrains("issuer_city_name")
    def _check_issuer_city_name(self):
        for record in self:
            if not record.issuer_city_name:
                raise ValidationError(_("O Município do Emitente é obrigatório."))

    # Sigla da UF do emitente.
    issuer_state = fields.Char(
        related="issuer_id.state_id.code",
        string="UF",
        store=True,
        size=2,
    )

    # Código do CEP do emitente. Informar zeros não significativos.
    issuer_zip = fields.Char(
        related="issuer_id.unformatted_zip",
        string="CEP",
        store=True,
        size=8,
    )

    # Código do País do emitente. 1058=Brasil. Opcional.
    issuer_country_code = fields.Integer(
        string="Código País",
        store=True,
        default=1058,
        readonly=True,
        size=4,
    )

    # Nome do País do emitente. Brasil ou BRASIL. Opcional.
    issuer_country_name = fields.Char(
        string="Nome País",
        store=True,
        size=60,
        compute="_compute_issuer_country_name",
    )

    @api.depends("issuer_id", "issuer_id.country_id")
    def _compute_issuer_country_name(self):
        for record in self:
            if record.issuer_id.country_id:
                record.issuer_country_name = record.issuer_id.country_id.with_context(
                    lang="pt_BR"
                ).name
            else:
                record.issuer_country_name = False

    @api.constrains("issuer_country_name")
    def _check_issuer_country_name(self):
        for record in self:
            if not record.issuer_country_name:
                raise ValidationError(_("O Nome do País do Emitente é obrigatório."))

    # Telefone do emitente. Preencher com DDD + número. Opcional.
    issuer_phone = fields.Char(
        related="issuer_id.phone",
        string="Telefone Emitente",
        store=True,
        size=14,
        # compute="_compute_issuer_phone",
    )

    # @api.depends("issuer_id.phone")
    # def _compute_issuer_phone(self):
    #     for record in self:
    #         if record.issuer_id.phone:
    #             return "".join(ch for ch in record.issuer_id.phone if ch.isdigit())
    #         else:
    #             record.issuer_phone = False

    # Inscrição Estadual do Emitente. Informar somente algarismos, sem formatação.
    issuer_ie = fields.Char(
        related="issuer_id.inscr_est",
        string="Inscrição Estadual Emitente",
        store=True,
        size=14,
        readonly=True,
    )

    @api.constrains("issuer_ie")
    def _check_issuer_ie(self):
        for record in self:
            if not record.issuer_ie:
                raise ValidationError(
                    _("A Inscrição Estadual do Emitente é obrigatória.")
                )

    # IE do Substituto Tributário da UF de destino da mercadoria. Opcional.
    # issuer_iest = fields.Char(string="IE Substituto Tributário Emitente", store=True, size=14)

    # Inscrição Municipal do Prestador de Serviço. Informado na emissão de NF-e conjugada. Opcional
    issuer_im = fields.Char(
        related="issuer_id.inscr_mun",
        string="Inscrição Municipal Emitente",
        store=True,
        size=15,
        readonly=True,
    )

    # CNAE fiscal. Opcional. Pode ser informado quando a Inscrição Municipal (C19) for informada.
    # issuer_cnae = fields.Char(related='issuer_id.cnae', string="CNAE Fiscal Emitente", store=True, size=7)

    # Código de Regime Tributário.
    # issuer_crt = fields.Selection(
    #     CRT_SELECTION, string="Código de Regime Tributário",
    # )

    issuer_fiscal_framework = fields.Selection(
        related="issuer_id.fiscal_framework",
        string="Regime Fiscal",
        store=True,
        readonly=True,
    )

    @api.constrains("issuer_fiscal_framework")
    def _check_issuer_fiscal_framework(self):
        for record in self:
            if not record.issuer_fiscal_framework:
                raise ValidationError(_("O Regime Fiscal do Emitente é obrigatório."))

    # === Grupo E. Identificação do Destinatário da NF-e  ===
    # Identificação do Destinatário da NF-e. Obrigatório para NF-e (modelo 55).

    recipient_id = fields.Many2one(
        comodel_name="res.partner",
        string="Destinatário",
        domain="[('country_id.code', '=', 'BR')]",
        required=True,
    )

    @api.constrains("recipient_id")
    def _check_recipient_id(self):
        for record in self:
            if record.document_model == "55" and not record.recipient_id:
                raise ValidationError(
                    _("Para NF-e modelo 55, o Destinatário é obrigatório.")
                )

    # CNPJ do destinatário
    recipient_cnpj = fields.Char(
        compute="_compute_recipient_cnpj",
        string="CNPJ do Destinatário",
        store=True,
        size=14,
        readonly=True,
    )

    @api.depends(
        "recipient_id",
        "recipient_id.company_type",
        "recipient_id.vat",
        "recipient_id.is_foreign",
    )
    def _compute_recipient_cnpj(self):
        for record in self:
            if (
                record.recipient_id.company_type == "company"
                and record.recipient_id.vat
                and len(record.recipient_id.vat) == 14
                and not record.recipient_id.is_foreign
            ):
                record.recipient_cnpj = record.recipient_id.vat
            else:
                record.recipient_cnpj = False

    @api.constrains("recipient_cnpj")
    def _check_recipient_cnpj(self):
        for record in self:
            if (
                record.recipient_id
                and record.recipient_id.company_type == "company"
                and not record.recipient_id.is_foreign
            ):
                if not record.recipient_cnpj:
                    raise ValidationError(_("O CNPJ do Destinatário é obrigatório."))
                elif not (len(record.recipient_cnpj) == 14):
                    raise ValidationError(
                        _("O CNPJ do Destinatário deve ter 14 caracteres.")
                    )

    # CPF do destinatário
    recipient_cpf = fields.Char(
        compute="_compute_recipient_cpf",
        string="CPF do Destinatário",
        store=True,
        size=11,
        readonly=True,
    )

    @api.depends(
        "recipient_id",
        "recipient_id.company_type",
        "recipient_id.vat",
        "recipient_id.is_foreign",
    )
    def _compute_recipient_cpf(self):
        for record in self:
            if (
                record.recipient_id.company_type == "person"
                and record.recipient_id.vat
                and len(record.recipient_id.vat) == 11
                and not record.recipient_id.is_foreign
            ):
                record.recipient_cpf = record.recipient_id.vat
            else:
                record.recipient_cpf = False

    @api.constrains("recipient_cpf")
    def _check_recipient_cpf(self):
        for record in self:
            if (
                record.recipient_id
                and record.recipient_id.company_type == "person"
                and not record.recipient_id.is_foreign
            ):
                if not record.recipient_cpf:
                    raise ValidationError(_("O CPF do Destinatário é obrigatório."))
                elif not (len(record.recipient_cpf) == 11):
                    raise ValidationError(
                        _("O CPF do Destinatário deve ter 11 caracteres.")
                    )

    # Identificação do destinatário no caso de comprador estrangeiro. Informar esta tag no caso de operação com o exterior
    recipient_foreign_id = fields.Char(
        compute="_compute_recipient_foreign_id",
        string="ID Estrangeiro Destinatário",
        store=True,
        size=20,
    )

    @api.depends("recipient_id", "recipient_id.vat", "recipient_id.is_foreign")
    def _compute_recipient_foreign_id(self):
        for record in self:
            if record.recipient_id.is_foreign:
                record.recipient_foreign_id = record.recipient_id.vat
            else:
                record.recipient_foreign_id = False

    @api.constrains("recipient_foreign_id")
    def _check_recipient_foreign_id(self):
        for record in self:
            if record.recipient_id and record.recipient_id.is_foreign:
                raise ValidationError(
                    _("O ID Estrangeiro do Destinatário é obrigatório.")
                )

    # Razão Social ou Nome do destinatário. Obrigatório para NF-e (modelo 55), opcional para NFC-e (modelo 65)
    recipient_legal_name = fields.Char(
        related="recipient_id.legal_name",
        string="Razão Social/Nome Destinatário",
        store=True,
        size=60,
    )

    @api.constrains("recipient_legal_name")
    def _check_recipient_legal_name(self):
        for record in self:
            if record.recipient_id and not record.recipient_legal_name:
                raise ValidationError(
                    _("A Razão Social/Nome do Destinatário é obrigatória.")
                )

    # Logradouro do destinatário.
    recipient_street = fields.Char(
        related="recipient_id.street",
        string="Logradouro Destinatário",
        store=True,
        size=60,
    )

    @api.constrains("recipient_street")
    def _check_recipient_street(self):
        for record in self:
            if record.recipient_id and not record.recipient_street:
                raise ValidationError(_("O Logradouro do Destinatário é obrigatório."))

    # Número do endereço do destinatário.
    recipient_street_number = fields.Char(
        related="recipient_id.street_number",
        string="Número Destinatário",
        store=True,
        size=60,
    )

    @api.constrains("recipient_street_number")
    def _check_recipient_street_number(self):
        for record in self:
            if record.recipient_id and not record.recipient_street_number:
                raise ValidationError(_("O Número do Destinatário é obrigatório."))

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

    @api.constrains("recipient_district")
    def _check_recipient_district(self):
        for record in self:
            if record.recipient_id and not record.recipient_district:
                raise ValidationError(_("O Bairro do Destinatário é obrigatório."))

    # Código do município do destinatário. Usar Tabela IBGE.
    recipient_city_code = fields.Char(
        related="recipient_id.city_id.ibge_code",
        string="Código Município Destinatário",
        store=True,
        size=7,
    )

    @api.constrains("recipient_city_code")
    def _check_recipient_city_code(self):
        for record in self:
            if record.recipient_id and not record.recipient_city_code:
                raise ValidationError(
                    _("O Código do Município do Destinatário é obrigatório.")
                )

    # Nome do município do destinatário. Informar 'EXTERIOR' para operações com o exterior.
    recipient_city_name = fields.Char(
        compute="_compute_recipient_city_name",
        string="Nome Município Destinatário",
        store=True,
        size=60,
    )

    @api.depends("recipient_id", "recipient_id.city_id", "recipient_id.is_foreign")
    def _compute_recipient_city_name(self):
        for record in self:
            if record.recipient_id.city_id:
                city_name = record.recipient_id.city_id.with_context(lang="pt_BR").name
                if city_name:
                    record.recipient_city_name = city_name
                else:
                    record.recipient_city_name = False
            elif record.recipient_id.is_foreign:
                record.recipient_city_name = "EXTERIOR"
            else:
                record.recipient_city_name = False

    @api.constrains("recipient_city_name")
    def _check_recipient_city_name(self):
        for record in self:
            if record.recipient_id and not record.recipient_city_name:
                raise ValidationError(
                    _("O Nome do Município do Destinatário é obrigatório.")
                )

    # Sigla da UF do destinatário. Informar 'EX' para operações com o exterior.
    recipient_state = fields.Char(
        compute="_compute_recipient_state",
        string="UF Destinatário",
        store=True,
        size=2,
    )

    @api.depends("recipient_id", "recipient_id.state_id", "recipient_id.is_foreign")
    def _compute_recipient_state(self):
        for record in self:
            if record.recipient_id.state_id:
                record.recipient_state = record.recipient_id.state_id.code
            elif record.recipient_id.is_foreign:
                record.recipient_state = "EX"
            else:
                record.recipient_state = False

    @api.constrains("recipient_state")
    def _check_recipient_state(self):
        for record in self:
            if record.recipient_id and not record.recipient_zip:
                raise ValidationError(_("A Sigla da UF do Destinatário é obrigatória."))

    # Código do CEP do destinatário. Informar zeros não significativos. Opcional.
    recipient_zip = fields.Char(
        related="recipient_id.unformatted_zip",
        string="CEP Destinatário",
        store=True,
        size=8,
        compute="_compute_recipient_zip",
    )

    @api.depends("recipient_id", "recipient_id.unformatted_zip")
    def _compute_recipient_zip(self):
        for record in self:
            if record.recipient_id.unformatted_zip:
                # preencher com zeros não significativos
                record.recipient_zip = record.recipient_id.unformatted_zip.zfill(8)
            else:
                record.recipient_zip = False

    # Código do País do destinatário. Usar Tabela BACEN. Opcional.
    recipient_country_code = fields.Integer(
        string="Código País Destinatário",
        store=True,
        default=1058,
        readonly=True,
        size=4,
    )

    # Nome do País do destinatário. Opcional.
    recipient_country_name = fields.Char(
        string="Nome País Destinatário",
        store=True,
        size=60,
        compute="_compute_recipient_country_name",
    )

    @api.depends("recipient_id.country_id")
    def _compute_recipient_country_name(self):
        for record in self:
            if record.recipient_id.country_id:
                record.recipient_country_name = (
                    record.recipient_id.country_id.with_context(lang="pt_BR").name
                )
            else:
                record.recipient_country_name = False

    @api.constrains("recipient_country_name")
    def _check_recipient_country_name(self):
        for record in self:
            if record.recipient_id and not record.recipient_country_name:
                raise ValidationError(
                    _("O Nome do País do Destinatário é obrigatório.")
                )

    # Telefone do destinatário. Preencher com o Código DDD + número do telefone. Nas operações com exterior é permitido informar o código do país + código da localidade + número do telefone (v2.0)
    recipient_phone = fields.Char(
        related="recipient_id.phone",
        string="Telefone Destinatário",
        #        compute="_compute_recipient_phone",
        store=True,
        size=14,
    )

    # def _compute_recipient_phone(self):
    #     for record in self:
    #         if record.recipient_id.phone and is_valid_phone(record.recipient_id.phone):
    #             return "".join(filter(str.isdigit, record.recipient_id.phone))
    #         else:
    #             record.recipient_phone = False

    # Indicador da IE do Destinatário. Para NFC-e ou operação com Exterior, informar 9 e não a tag IE.
    recipient_ie_indicator = fields.Selection(
        RECIPIENT_IE_INDICATOR,
        string="Indicador da IE do Destinatário",
        compute="_compute_recipient_ie_indicator",
    )

    @api.depends(
        "recipient_id",
        "document_model",
        "recipient_id.is_foreign",
        "recipient_id.company_type",
        "recipient_id.no_inscr_est",
    )
    def _compute_recipient_ie_indicator(self):
        for record in self:
            if record.recipient_id:
                if (
                    record.recipient_id.is_foreign
                    or record.recipient_id.company_type == "person"
                ):
                    record.recipient_ie_indicator = "9"
                elif record.recipient_id.no_inscr_est:
                    record.recipient_ie_indicator = "2"
                else:
                    record.recipient_ie_indicator = "1"
            else:
                record.recipient_ie_indicator = False

    @api.constrains("recipient_ie_indicator")
    def _check_recipient_ie_indicator(self):
        for record in self:
            if record.recipient_id and not record.recipient_ie_indicator:
                raise ValidationError(
                    _("O Indicador da IE do Destinatário é obrigatório.")
                )

    # Inscrição Estadual do Destinatário. Obrigatorio se o indicador da IE do Destinatário for 1
    recipient_ie = fields.Char(
        string="Inscrição Estadual Destinatário",
        compute="_compute_recipient_ie",
        # related="recipient_id.inscr_est",
        store=True,
        size=14,
    )

    @api.depends("recipient_ie_indicator", "recipient_id", "recipient_id.inscr_est")
    def _compute_recipient_ie(self):
        for record in self:
            if record.recipient_ie_indicator == "1" and record.recipient_id.inscr_est:
                record.recipient_ie = record.recipient_id.inscr_est
            else:
                record.recipient_ie = False

    @api.constrains("recipient_ie")
    def _check_recipient_ie(self):
        for record in self:
            if (
                record.recipient_id
                and record.recipient_ie_indicator == "1"
                and not record.recipient_ie
            ):
                raise ValidationError(
                    _("A Inscrição Estadual do Destinatário é obrigatória.")
                )

    # Inscrição na SUFRAMA. Obrigatório em operações com incentivos fiscais SUFRAMA. Opcional.
    recipient_suframa = fields.Char(
        related="recipient_id.suframa",
        string="IE SUFRAMA Destinatário",
        store=True,
        size=9,
    )

    # # Campo opcional, pode ser informado na NF-e conjugada, com itens de produtos sujeitos ao ICMS e itens de serviços sujeitos ao ISSQN.
    # recipient_im = fields.Char(
    #     related="recipient_id.inscr_mun",
    #     string="Inscrição Municipal Destinatário",
    #     store=True,
    #     size=15,
    # )

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

    @api.constrains("authorized_xml_access_ids")
    def _check_authorized_xml_access_ids(self):
        for record in self:
            if record.authorized_xml_access_ids:
                for authorized_xml_access_id in record.authorized_xml_access_ids:
                    if authorized_xml_access_id.company_type == "person" and (
                        not authorized_xml_access_id.vat
                        or (
                            not authorized_xml_access_id.vat.isdigit()
                            and len(authorized_xml_access_id.vat) != 11
                        )
                    ):
                        raise ValidationError(
                            _(
                                "As Pessoas Autorizadas a Acessar XML devem ter um CPF válido."
                            )
                        )
                    if authorized_xml_access_id.company_type == "company" and (
                        not authorized_xml_access_id.vat
                        or len(authorized_xml_access_id.vat) != 14
                    ):
                        raise ValidationError(
                            _(
                                "As Pessoas Autorizadas a Acessar XML devem ter um CNPJ válido."
                            )
                        )

    # === Grupo H. Detalhamento de Produtos e Serviços da NF-e  ===
    # det - Detalhamento de Produtos e Serviços. Múltiplas ocorrências (máximo = 990).

    invoice_line_ids = fields.One2many(
        comodel_name="l10n_br_nfe.nfe.document.line",
        inverse_name="nfe_id",
        string="Itens da Nota Fiscal",
    )

    # === Grupo W. Total da NF-e  ===
    # total - Totais da NF-e

    # Totais do ICMS

    # Base de Cálculo do ICMS.
    total_icms_base = fields.Float(
        string="BC do ICMS",
        digits=(13, 2),
        compute="_compute_total_icms_base",
        store=True,
    )

    def _is_issuer_simples_nacional(self):
        return self.issuer_id.fiscal_framework in ("1", "2")

    @api.depends("issuer_id", "issuer_id.fiscal_framework", "invoice_line_ids")
    def _compute_total_icms_base(self):
        for record in self:
            if record._is_issuer_simples_nacional():
                record.total_icms_base = 0.00
            else:
                record.total_icms_base = sum(
                    record.invoice_line_ids.mapped("icms_bc_value")
                )

    total_icms = fields.Float(
        string="Valor Total do ICMS",
        digits=(13, 2),
        compute="_compute_total_icms",
        store=True,
    )

    @api.depends("issuer_id", "issuer_id.fiscal_framework", "invoice_line_ids")
    def _compute_total_icms(self):
        for record in self:
            if record._is_issuer_simples_nacional():
                record.total_icms = 0.00
            else:
                record.total_icms = sum(record.invoice_line_ids.mapped("icms_value"))

    # Valor Total do ICMS.

    # soma do valor do icms desonerado dos items, nao implementado
    total_icms_deson = fields.Float(string="Valor ICMS Desonerado", digits=(13, 2))
    # Valor Total do ICMS desonerado.

    # == icms difal ==

    # Valor Total do Fundo de Combate à Pobreza da UF de Destino.
    total_fcp_uf_dest = fields.Float(
        string="Valor Total FCP da UF de Destino", digits=(13, 2)
    )

    # Valor Total do ICMS da UF de Destino.
    total_icms_uf_dest = fields.Float(
        string="Valor Total do ICMS da UF de Destino", digits=(13, 2)
    )

    total_icms_interestadual = fields.Float(
        string="Valor Total do ICMS Interestadual", digits=(13, 2)
    )

    # Valor Total do Fundo de Combate à Pobreza.
    total_fcp = fields.Float(
        string="Valor Total FCP",
        digits=(13, 2),
        compute="_compute_total_fcp",
        store=True,
    )

    def _compute_total_fcp(self):
        for record in self:
            if record._is_issuer_simples_nacional():
                record.total_fcp = 0.00
            else:
                record.total_fcp = sum(record.invoice_line_ids.mapped("icms_fcp_value"))

    # Valor Total da Base de Calculo do ICMS ST.
    total_icms_st_base = fields.Float(
        string="Valor Total da Base de Calculo do ICMS ST",
        digits=(13, 2),
        compute="_compute_total_icms_st_base",
        store=True,
    )

    @api.depends("issuer_id", "issuer_id.fiscal_framework", "invoice_line_ids")
    def _compute_total_icms_st_base(self):
        for record in self:
            if record._is_issuer_simples_nacional():
                record.total_icms_st_base = 0.00
            else:
                record.total_icms_st_base = sum(
                    record.invoice_line_ids.mapped("icms_st_bc_value")
                )

    # Valor Total do ICMS ST.
    total_icms_st_value = fields.Float(
        string="Valor Total do ICMS ST",
        digits=(13, 2),
        compute="_compute_total_icms_st_value",
        store=True,
    )

    @api.depends("issuer_id", "issuer_id.fiscal_framework", "invoice_line_ids")
    def _compute_total_icms_st_value(self):
        for record in self:
            if record._is_issuer_simples_nacional():
                record.total_icms_st_value = 0.00
            else:
                record.total_icms_st_value = sum(
                    record.invoice_line_ids.mapped("icms_st_value")
                )

    # Valor Total do FCP retido por Substituição Tributária.
    total_icms_st_fcp = fields.Float(
        string="Valor Total FCP ST",
        digits=(13, 2),
        compute="_compute_total_icms_st_fcp",
        store=True,
    )

    def _compute_total_icms_st_fcp(self):
        for record in self:
            if record._is_issuer_simples_nacional():
                record.total_icms_st_fcp = 0.00
            else:
                record.total_icms_st_fcp = sum(
                    record.invoice_line_ids.mapped("icms_st_fcp_value")
                )

    # Valor Total do FCP ST Retido Anteriormente por Substituição Tributária.
    total_icms_fcp_st_retention = fields.Float(
        string="Valor Total do FCP ST Retido Anteriormente por Substituição Tributária",
        digits=(13, 2),
    )

    # Valor Total dos Produtos e Serviços.
    total_products = fields.Float(
        string="Valor Total dos Produtos e Serviços",
        # required=True,
        digits=(13, 2),
        store=True,
        compute="_compute_total_products",
    )

    @api.depends("invoice_line_ids")
    def _compute_total_products(self):
        for record in self:
            if len(record.invoice_line_ids) == 0:
                record.total_products = 0.00
            else:
                record.total_products = sum(
                    record.invoice_line_ids.mapped("total_value")
                )

    # Valor Total do Frete.
    total_freight = fields.Float(
        string="Valor Total do Frete",
        digits=(13, 2),
        compute="_compute_total_freight",
        store=True,
        readonly=False,
    )

    @api.depends("invoice_line_ids")
    def _compute_total_freight(self):
        for record in self:
            if not record.total_freight:
                record.total_freight = sum(
                    record.invoice_line_ids.mapped("freight_value")
                )

    @api.constrains("total_freight")
    def _check_total_freight_minimum(self):
        """Ensure total_freight is not smaller than the sum of invoice line freight values"""
        for record in self:
            computed_sum = sum(record.invoice_line_ids.mapped("freight_value"))
            if record.total_freight < computed_sum:
                raise ValidationError(
                    _(
                        "O frete total (%.2f) não pode ser menor que a soma dos fretes atribuidos aos produtos (%.2f)."
                    )
                    % (record.total_freight, computed_sum)
                )

    # Valor Total do Seguro.
    total_insurance = fields.Float(
        string="Valor Total do Seguro",
        digits=(13, 2),
        compute="_compute_total_insurance",
        store=True,
        readonly=False,
    )

    @api.depends("invoice_line_ids")
    def _compute_total_insurance(self):
        for record in self:
            if not record.total_insurance:
                record.total_insurance = sum(
                    record.invoice_line_ids.mapped("insurance_value")
                )

    @api.constrains("total_insurance")
    def _check_total_insurance_minimum(self):
        """Ensure total_insurance is not smaller than the sum of invoice line insurance values"""
        for record in self:
            computed_sum = sum(record.invoice_line_ids.mapped("insurance_value"))
            if record.total_insurance < computed_sum:
                raise ValidationError(
                    _(
                        "O seguro total (%.2f) não pode ser menor que a soma dos seguros atribuidos aos produtos (%.2f)."
                    )
                    % (record.total_insurance, computed_sum)
                )

    # Valor Total do Desconto.
    total_discount = fields.Float(
        string="Valor Total do Desconto",
        digits=(13, 2),
        compute="_compute_total_discount",
        store=True,
        readonly=False,
    )

    @api.depends("invoice_line_ids")
    def _compute_total_discount(self):
        for record in self:
            if not record.total_discount:
                record.total_discount = sum(
                    record.invoice_line_ids.mapped("discount_value")
                )

    @api.constrains("total_discount")
    def _check_total_discount_minimum(self):
        """Ensure total_discount is not smaller than the sum of invoice line discount values"""
        for record in self:
            computed_sum = sum(record.invoice_line_ids.mapped("discount_value"))
            if record.total_discount < computed_sum:
                raise ValidationError(
                    _(
                        "O desconto total (%.2f) não pode ser menor que a soma dos descontos atribuidos aos produtos (%.2f)."
                    )
                    % (record.total_discount, computed_sum)
                )

    total_ii = fields.Float(
        string="Valor Total do Imposto de Importação",
        digits=(13, 2),
        default=0.00,
        readonly=True,
    )
    # Valor Total do Imposto de Importação.

    total_ipi = fields.Float(
        string="Valor Total do IPI",
        digits=(13, 2),
        compute="_compute_total_ipi",
        store=True,
    )
    # Valor Total do IPI.

    @api.depends("issuer_id", "issuer_id.fiscal_framework", "invoice_line_ids")
    def _compute_total_ipi(self):
        for record in self:
            if record._is_issuer_simples_nacional():
                record.total_ipi = 0.00
            else:
                record.total_ipi = sum(record.invoice_line_ids.mapped("ipi_value"))

    total_ipi_returned = fields.Float(
        string="Valor Total do IPI Devolvido",
        digits=(13, 2),
        compute="_compute_total_ipi_returned",
        store=True,
    )
    # Valor Total do IPI Devolvido.

    @api.depends("invoice_line_ids")
    def _compute_total_ipi_returned(self):
        for record in self:
            record.total_ipi_returned = sum(
                record.invoice_line_ids.mapped("total_ipi_returned")
            )

    total_pis = fields.Float(
        string="Valor Total do PIS",
        digits=(13, 2),
        compute="_compute_total_pis",
        store=True,
    )
    # Valor Total do PIS.

    @api.depends("invoice_line_ids")
    def _compute_total_pis(self):
        for record in self:
            if record._is_issuer_simples_nacional():
                record.total_pis = 0.00
            else:
                record.total_pis = sum(record.invoice_line_ids.mapped("pis_value"))

    total_cofins = fields.Float(string="Valor Total da COFINS", digits=(13, 2))
    # Valor Total da COFINS.

    @api.depends("invoice_line_ids")
    def _compute_total_cofins(self):
        for record in self:
            if record._is_issuer_simples_nacional():
                record.total_cofins = 0.00
            else:
                record.total_cofins = sum(
                    record.invoice_line_ids.mapped("cofins_value")
                )

    total_other_expenses = fields.Float(
        string="Outras Despesas Acessórias",
        digits=(13, 2),
    )
    # Outras Despesas acessórias.

    # Valor Total da NF-e.
    total_nfe = fields.Float(
        string="Valor Total da NF-e",
        required=True,
        digits=(13, 2),
        compute="_compute_total_nfe",
    )

    @api.depends("invoice_line_ids")
    def _compute_total_nfe(self):
        for record in self:
            record.total_nfe = (
                record.total_products
                - record.total_discount
                - record.total_icms_deson
                + record.total_icms_st_value
                + record.total_icms_st_fcp
                + record.total_freight
                + record.total_insurance
                + record.total_other_expenses
                + record.total_ii
                + record.total_ipi
                + record.total_ipi_returned
            )

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

    # Grupo X. Informações do Transporte da NF-e
    # Modalidade de Frete.
    freight_modality = fields.Selection(
        string="Modalidade de Frete",
        selection=FREIGHT_MODALITY,
        required=True,
        default="9",
    )

    # === Grupo Y. Dados da Cobrança  ===
    #  Dados da Fatura

    # Número da Fatura. Opcional.
    billing_number = fields.Char(string="Número da Fatura", size=60)

    # Valor Original da Fatura.
    billing_original_value = fields.Float(
        string="Valor Original da Fatura",
        digits=(13, 2),
        compute="_compute_billing_original_value",
        store=True,
        readonly=False,
    )

    @api.depends("total_nfe")
    def _compute_billing_original_value(self):
        for record in self:
            if not record.billing_original_value:
                record.billing_original_value = record.total_nfe

    # Valor do Desconto da Fatura.
    billing_discount_value = fields.Float(
        string="Valor do Desconto da Fatura", digits=(13, 2)
    )

    # Valor Líquido da Fatura.
    billing_liquid_value = fields.Float(
        string="Valor Líquido da Fatura",
        digits=(13, 2),
        compute="_compute_billing_liquid_value",
        store=True,
    )

    @api.depends("billing_original_value", "billing_discount_value")
    def _compute_billing_liquid_value(self):
        for record in self:
            record.billing_liquid_value = (
                record.billing_original_value - record.billing_discount_value
            )

    billing_installment_ids = fields.One2many(
        comodel_name="l10n_br_nfe.nfe.document.installment",
        inverse_name="nfe_id",
        string="Parcelas da Fatura",
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

    remaining_payment_value = fields.Float(
        string="Valor Restante do Pagamento",
        digits=(13, 2),
        compute="_compute_remaining_payment_value",
        readonly=True,
    )

    @api.depends("payment_detail_ids.payment_value", "total_nfe")
    def _compute_remaining_payment_value(self):
        for record in self:
            record.remaining_payment_value = record.total_nfe - sum(
                record.payment_detail_ids.mapped("payment_value")
            )

    payment_detail_ids = fields.One2many(
        comodel_name="l10n_br_nfe.nfe.document.payment",
        inverse_name="nfe_id",
        string="Detalhes do Pagamento",
    )

    @api.constrains("payment_detail_ids", "total_nfe")
    def _check_payment_detail_ids(self):
        for record in self:
            if len(record.payment_detail_ids) == 0:
                raise ValidationError(_("Deve ter pelo menos um detalhe de pagamento."))
            if record.total_nfe != sum(
                record.payment_detail_ids.mapped("payment_value")
            ):
                raise ValidationError(
                    _(
                        "O valor total da NF-e deve ser igual ao valor total dos pagamentos."
                    )
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

    mandatory_additional_information_ids = fields.Many2many(
        comodel_name="l10n_br_nfe.nfe.additional_information",
        string="Informações Adicionais Obrigatórias",
        compute="_compute_mandatory_additional_information_ids",
        relation="nfe_additional_information_rel",
        store=True,
    )

    @api.depends("issuer_id", "issuer_id.fiscal_framework")
    def _compute_mandatory_additional_information_ids(self):
        for record in self:
            print("record.issuer_id", record.issuer_id)
            print(
                "record.issuer_id.fiscal_framework", record.issuer_id.fiscal_framework
            )
            external_ids = []
            if record.issuer_id and record.issuer_id.fiscal_framework in (
                "1",
                "2",
            ):
                external_ids = [
                    "l10n_br_nfe.add_info_simples_nacional",
                    "l10n_br_nfe.add_info_nao_gera_credito_fiscal_ipi",
                ]

            if external_ids:
                records = self.env["l10n_br_nfe.nfe.additional_information"].browse()
                for xml_id in external_ids:
                    records += self.env.ref(xml_id)
                record.mandatory_additional_information_ids = records

            else:
                record.mandatory_additional_information_ids = self.env[
                    "l10n_br_nfe.nfe.additional_information"
                ]

    mandatory_additional_information = fields.Text(
        string="Informações Adicionais Obrigatórias",
        compute="_compute_mandatory_additional_information",
        store=True,
    )

    @api.depends("mandatory_additional_information_ids")
    def _compute_mandatory_additional_information(self):
        for record in self:
            # Filter out empty/False values
            info_values = record.mandatory_additional_information_ids.mapped(
                "additional_information"
            )
            # Join only non-empty strings
            record.mandatory_additional_information = "\n".join(
                filter(None, info_values)
            )

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

    @api.constrains("series_id", "nfe_number", "emission_type")
    def _check_unique_nfe_natural_key(self):
        # Validação da Chave Natural (UF, CNPJ/CPF do Emitente, Série, Número, Modelo, Ambiente de Autorização/Tipo de Emissão)
        # O Sistema de Autorização de Uso da SEFAZ rejeita pedidos de autorização duplicados de Chave Natural.
        for record in self:
            domain = [
                ("document_model", "=", record.document_model),
                ("nfe_series", "=", f"{record.series_id.series}"),
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

    # @api.constrains("danfe_print_format", "emission_type")
    # def _check_danfe_contingency_nfc_e(self):
    #     # NFC-e (modelo 65) não permite emissão em contingência usando EPEC ou formulário de segurança (tpEmis != 4, 5)
    #     # Para NFC-e (modelo 65) tpEmis só pode ser 9 (Contingência Off-Line) ou, a critério da UF, 4 (Contingência EPEC).
    #     for record in self:
    #         if record.document_model == "65":  # NFC-e
    #             if record.emission_type not in [
    #                 "1",
    #                 "9",
    #                 "4",
    #             ]:  # Normal, Off-line, EPEC
    #                 raise ValidationError(
    #                     _(
    #                         "Tipo de Emissão inválido para NFC-e. Apenas Normal (1), Contingência Off-Line (9) e EPEC (4) são permitidos."
    #                     )
    #                 )
    #             if (
    #                 record.danfe_print_format in ["1", "2", "3"]
    #                 and record.emission_type != "1"
    #             ):
    #                 raise ValidationError(
    #                     _(
    #                         "DANFE normal/simplificado só pode ser gerado para NFC-e em emissão normal."
    #                     )
    #                 )

    # @api.constrains("emission_type")
    # def _check_contingency_justification(self):
    #     # Se emissão normal (tpEmis = 1-Normal): dhCont e xJust não devem ser informados.
    #     # Se emissão em contingência utilizando DPEC, formulário de segurança ou contingência off-line (tpEmis = 2, 4, 5 ou 9):
    #     # dhCont e xJust devem ser informados.
    #     # Nota: dhCont e xJust não são campos no modelo Odoo simplificado, mas seriam validados se presentes.
    #     pass

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("nfe_number"):  # Só gerar se não existir
                # Generate nfe_number before creation
                # You'll need to adapt this based on your _generate_nfe_number logic
                vals["nfe_number"] = self._generate_nfe_number(vals)

        records = super().create(vals_list)
        for record in records:
            if not record.access_key:
                # Generate access_key before creation
                record.access_key = record.generate_access_key()
        return records

    def _generate_nfe_number(self, vals):
        """Gera o número da NFe de forma controlada"""
        # self.ensure_one()

        series_id = vals.get("series_id")
        if not series_id:
            raise ValidationError("Série é obrigatória para gerar o número da NFe")

        # Get the series record and call next_seq_number()
        series = self.env["l10n_br_nfe.nfe.series"].browse(series_id)
        nfe_number = series.next_seq_number()

        return nfe_number

    def generate_access_key(self):
        uf_code = self.issuer_state_code
        year_month_day = fields.Datetime.from_string(self.issue_datetime).strftime(
            "%y%m"
        )  # vals.get("issue_datetime").strftime("%y%m")
        issuer_document = self.issuer_cnpj or self.issuer_cpf
        padded_issuer_document = issuer_document.zfill(14)
        document_model = self.document_model
        series = str(self.nfe_series)
        padded_series = series.zfill(3)
        nfe_number = str(self.nfe_number)
        padded_nfe_number = nfe_number.zfill(9)
        emission_type = self.emission_type
        random_number = self.random_number

        number_without_dv = f"{uf_code}{year_month_day}{padded_issuer_document}{document_model}{padded_series}{padded_nfe_number}{emission_type}{random_number}"

        dv = self._calculate_mod11_dv(number_without_dv)

        return f"{number_without_dv}{dv}"

    def _calculate_mod11_dv(self, key_without_dv):
        """
        Calcula o dígito verificador usando algoritmo módulo 11 base 2,9
        para chave de acesso da NFe

        Args:
            key_without_dv (str): Chave de 43 dígitos sem o DV

        Returns:
            int: Dígito verificador (0-9)
        """
        if not key_without_dv or len(key_without_dv) != 43:
            raise ValidationError(
                f"Chave deve ter 43 dígitos. Recebido: {len(key_without_dv)} dígitos"
            )

        # Sequência de multiplicadores: 2,3,4,5,6,7,8,9,2,3,4,5,6,7,8,9,...
        multipliers = [2, 3, 4, 5, 6, 7, 8, 9]

        # Inverter a chave para processar da direita para esquerda
        reversed_key = key_without_dv[::-1]

        total = 0

        # Multiplicar cada dígito pelo multiplicador correspondente
        for i, digit in enumerate(reversed_key):
            multiplier = multipliers[i % 8]  # Ciclar pelos multiplicadores
            product = int(digit) * multiplier
            total += product

        # Calcular o resto da divisão por 11
        remainder = total % 11

        # Regra do módulo 11 para NFe:
        # Quando o resto da divisão for 0 (zero) ou 1 (um), o DV deverá ser igual a 0 (zero).
        # Se resto >= 2: DV = 11 - resto
        if remainder < 2:
            dv = 0
        else:
            dv = 11 - remainder

        return dv

    def action_generate_nfe(self):
        printNfeXml(self)
        print("action", self)
