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

    if nfe_document.issuer_phone:
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

    if nfe_document.authorized_xml_access_ids:
        autXML = etree.SubElement(root, "autXML")
        for authorized_xml_access_id in nfe_document.authorized_xml_access_ids:
            if (
                authorized_xml_access_id.company_type == "company"
                and len(authorized_xml_access_id.vat) == 14
            ):
                idEstrangeiro = etree.SubElement(autXML, "CNPJ")
                idEstrangeiro.text = authorized_xml_access_id.vat
            elif (
                authorized_xml_access_id.company_type == "person"
                and len(authorized_xml_access_id.vat) == 11
                and authorized_xml_access_id.vat.isdigit()
            ):
                idEstrangeiro = etree.SubElement(autXML, "CPF")
                idEstrangeiro.text = authorized_xml_access_id.vat

    for item in nfe_document.invoice_line_ids:
        det = etree.SubElement(root, "det")
        det.set("nItem", str(item.item_number))

        prod = etree.SubElement(det, "prod")

        cProd = etree.SubElement(prod, "cProd")
        cProd.text = item.product_code

        if not item.product_id.no_barcode and not item.product_id.barcode:
            raise ValidationError(
                _(
                    "Geração de XML: O produto '%s' não possui código de barras mas não está marcado como 'Não possui código de barras' no cadastro do produto. Atualize o cadastro do produto da forma correta. Não informar o código de barras na nota fiscal quando o produto possuir código de barras é uma falha de obrigação fiscal acessória e está sujeita a multa."
                )
                % item.product_id.name
            )
        elif item.product_id.no_barcode and item.product_id.barcode:
            raise ValidationError(
                _(
                    "Geração de XML: O produto '%s' possui código de barras mas está marcado como 'Não possui código de barras' no cadastro do produto. Atualize o cadastro do produto da forma correta. Não informar o código de barras na nota fiscal quando o produto possuir código de barras é uma falha de obrigação fiscal acessória e está sujeita a multa."
                )
                % item.product_id.name
            )

        if item.product_id.barcode:
            cEAN = etree.SubElement(prod, "cEAN")
            cEAN.text = item.product_id.barcode
        else:
            cEAN = etree.SubElement(prod, "cEAN")
            cEAN.text = "SEM GTIN"

        xProd = etree.SubElement(prod, "xProd")
        xProd.text = item.product_description

        NCM = etree.SubElement(prod, "NCM")
        NCM.text = item.product_id.ncm_id.code_unmasked

        if item.product_id.cest_id:
            CEST = etree.SubElement(prod, "CEST")
            CEST.text = item.product_id.cest_id.code_unmasked

        cfop = etree.SubElement(prod, "CFOP")
        cfop.text = item.cfop_code

        uCom = etree.SubElement(prod, "uCom")
        uCom.text = item.unit

        qCom = etree.SubElement(prod, "qCom")
        qCom.text = f"{item.quantity:.4f}"

        vUnCom = etree.SubElement(prod, "vUnCom")
        vUnCom.text = f"{item.unit_price:.10f}"

        vProd = etree.SubElement(prod, "vProd")
        vProd.text = f"{item.total_value:.2f}"

        cEANTrib = etree.SubElement(prod, "cEANTrib")
        cEANTrib.text = item.gtin_trib

        uTrib = etree.SubElement(prod, "uTrib")
        uTrib.text = item.unit_trib

        qTrib = etree.SubElement(prod, "qTrib")
        qTrib.text = f"{item.quantity_trib:.4f}"

        vUnTrib = etree.SubElement(prod, "vUnTrib")
        vUnTrib.text = f"{item.unit_value_trib:.10f}"

        if item.freight_value:
            vFrete = etree.SubElement(prod, "vFrete")
            vFrete.text = f"{item.freight_value:.2f}"

        if item.insurance_value:
            vSeg = etree.SubElement(prod, "vSeg")
            vSeg.text = f"{item.insurance_value:.2f}"

        if item.discount_value:
            vDesc = etree.SubElement(prod, "vDesc")
            vDesc.text = f"{item.discount_value:.2f}"

        if item.other_expenses_value:
            vOutro = etree.SubElement(prod, "vOutro")
            vOutro.text = f"{item.other_expenses_value:.2f}"

        indTot = etree.SubElement(prod, "indTot")
        indTot.text = item.include_in_total

        imposto = etree.SubElement(det, "imposto")

        # Grupo N - ICMS
        icms = etree.SubElement(imposto, "ICMS")
        buildICMS(icms, item, nfe_document.final_customer_operation == "1")
        buildIPI(imposto, item)

        buildPIS(imposto, item)
        buildCOFINS(imposto, item)

        buildIPIReturned(imposto, item)

        if item.additional_information:
            additional_information = etree.SubElement(det, "infAdProd")
            additional_information.text = item.additional_information

    # 101 - Tributada pelo Simples Nacional com permissão de crédito
    # 102 - Tributada pelo Simples Nacional sem permissão de crédito
    # 103 - Isenção do ICMS no Simples Nacional para faixa de receita bruta
    # 201 - Tributada pelo Simples Nacional com permissão de crédito e com cobrança do ICMS por substituição tributária
    # 202 - Tributada pelo Simples Nacional sem permissão de crédito e com cobrança do ICMS por substituição tributária
    # 203 - Isenção do ICMS no Simples Nacional para faixa de receita bruta e com cobrança do ICMS por substituição tributária
    # 300 - Imune
    # 400 - Não tributada pelo Simples Nacional
    # 500 - ICMS cobrado anteriormente por substituição tributária (substituído) ou por antecipação
    # 900 - Outros

    return root


def buildIPIReturned(root, line):
    # todo checar se é nota
    recipient_fiscal_framework = line.nfe_id.recipient_fiscal_framework
    is_return_fiscal_document = line.nfe_id.emission_finality == "4"

    if not is_return_fiscal_document:
        return

    if recipient_fiscal_framework in ("1", "2"):
        raise ValidationError(
            _(
                f"Geração de XML: (Produto: {line.product_description})"
                f"Grupo IPI Devolvido não deve ser informado se o regime fiscal do destinatário for Simples Nacional."
            )
        )
    elif recipient_fiscal_framework == "3":
        ipi_returned_fields = [
            line.total_ipi_returned,
            line.total_product_returned_percentage,
        ]
        if any(ipi_returned_fields) and not all(ipi_returned_fields):
            raise ValidationError(
                _(
                    f"Geração de XML: (Produto: {line.product_description})"
                    f"Grupo IPI Devolvido deve ser informado com todos os campos: Valor Total do IPI Devolvido e Percentual da Mercadoria Devolvida."
                )
            )

        impostoDevol = etree.SubElement(root, "impostoDevol")

        pDevol = etree.SubElement(impostoDevol, "pDevol")
        pDevol.text = f"{line.total_ipi_returned:.2f}"

        ipi = etree.SubElement(impostoDevol, "IPI")

        vIPIDevol = etree.SubElement(ipi, "vIPIDevol")
        vIPIDevol.text = f"{line.total_ipi_returned:.2f}"


def buildIPI(root, line):
    issuer_fiscal_framework = line.nfe_id.issuer_fiscal_framework

    if issuer_fiscal_framework in ("1", "2"):
        if not line.product_id.fiscal_type_id.code in ("03", "04", "05", "06"):
            # se não for um produto fabricado, o grupo IPI não é informado
            return

        ipi = etree.SubElement(root, "IPI")

        cEnq = etree.SubElement(ipi, "cEnq")
        cEnq.text = "999"

        IPITrib = etree.SubElement(ipi, "IPITrib")

        CST = etree.SubElement(IPITrib, "CST")
        CST.text = "99"

    else:
        raise ValidationError(
            _(
                f"Geração de XML: (Produto: {line.product_description})"
                f"Grupo IPI não é suportado ainda para o regime normal."
            )
        )


def buildPIS(root, line):
    issuer_fiscal_framework = line.nfe_id.issuer_fiscal_framework

    if issuer_fiscal_framework in ("1", "2"):
        pis = etree.SubElement(root, "PIS")

        PISOutr = etree.SubElement(pis, "PISOutr")

        CST = etree.SubElement(PISOutr, "CST")
        CST.text = "99"

        qBCProd = etree.SubElement(PISOutr, "qBCProd")
        qBCProd.text = "0.0000"

        vAliqProd = etree.SubElement(PISOutr, "vAliqProd")
        vAliqProd.text = "0.0000"

        vPIS = etree.SubElement(PISOutr, "vPIS")
        vPIS.text = "0.00"

    else:
        raise ValidationError(
            _(
                f"Geração de XML: (Produto: {line.product_description})"
                f"Grupo PIS não é suportado ainda para o regime normal."
            )
        )


def buildCOFINS(root, line):
    issuer_fiscal_framework = line.nfe_id.issuer_fiscal_framework

    if issuer_fiscal_framework in ("1", "2"):
        cofins = etree.SubElement(root, "COFINS")

        COFINSOutr = etree.SubElement(cofins, "COFINSOutr")

        CST = etree.SubElement(COFINSOutr, "CST")
        CST.text = "99"

        qBCProd = etree.SubElement(COFINSOutr, "qBCProd")
        qBCProd.text = "0.0000"

        vAliqProd = etree.SubElement(COFINSOutr, "vAliqProd")
        vAliqProd.text = "0.0000"

        vCOFINS = etree.SubElement(COFINSOutr, "vCOFINS")
        vCOFINS.text = "0.00"
    else:
        raise ValidationError(
            _(
                f"Geração de XML: (Produto: {line.product_description})"
                f"Grupo COFINS não é suportado ainda para o regime normal."
            )
        )


def buildICMS(icms_root, nfe_document_line, is_final_customer):
    """
    Constrói o XML do ICMS conforme layout NFe 4.00

    Args:
        icms_root: Elemento <ICMS> onde serão adicionados os subelementos
        nfe_document_line: Linha do documento NFe com os dados tributários
    """
    # Determina se é Simples Nacional (CSOSN) ou Regime Normal (CST)
    icms_cst_code = nfe_document_line.icms_cst_code
    icms_origin = nfe_document_line.icms_origin
    issuer_fiscal_framework = nfe_document_line.nfe_id.issuer_fiscal_framework

    # Simples Nacional - CSOSN (101, 102, 103, 201, 202, 203, 300, 400, 500, 900)
    if issuer_fiscal_framework in ("1", "2"):
        _buildICMSSN(
            icms_root, nfe_document_line, icms_origin, icms_cst_code, is_final_customer
        )
    # Regime Normal - CST (00, 10, 20, 30, 40, 41, 50, 51, 60, 70, 90)
    # else:
    #    #  TODO: Implementar
    #    #  _buildICMSRegimeNormal(icms_root, nfe_document_line, icms_origin, icms_cst_code)


def _buildICMSRegimeNormal(icms_root, line, origin, cst):
    """Constrói XML ICMS para Regime Normal conforme Manual NFe 4.00"""

    if cst == "00":
        # N02 - Tributada integralmente
        icms00 = etree.SubElement(icms_root, "ICMS00")

        # N11 - Origem da mercadoria (obrigatório)
        orig = etree.SubElement(icms00, "orig")
        orig.text = origin

        # N12 - CST (obrigatório)
        CST = etree.SubElement(icms00, "CST")
        CST.text = cst

        # N13 - Modalidade BC (obrigatório)
        modBC = etree.SubElement(icms00, "modBC")
        modBC.text = line.icms_bc_modality or "3"

        # N15 - Valor BC (obrigatório)
        vBC = etree.SubElement(icms00, "vBC")
        vBC.text = f"{line.icms_bc_value:.2f}"

        # N16 - Alíquota (obrigatório)
        pICMS = etree.SubElement(icms00, "pICMS")
        pICMS.text = f"{line.icms_tax_percent:.2f}"

        # N17 - Valor ICMS (obrigatório)
        vICMS = etree.SubElement(icms00, "vICMS")
        vICMS.text = f"{line.icms_value:.2f}"

        # N17b - Base FCP (opcional)
        if line.icms_fcp_bc_value:
            vBCFCP = etree.SubElement(icms00, "vBCFCP")
            vBCFCP.text = f"{line.icms_fcp_bc_value:.2f}"

            # N17c - Percentual FCP (opcional)
            if line.icms_fcp_tax_percent:
                pFCP = etree.SubElement(icms00, "pFCP")
                pFCP.text = f"{line.icms_fcp_tax_percent:.2f}"

            # N17d - Valor FCP (opcional)
            if line.icms_fcp_value:
                vFCP = etree.SubElement(icms00, "vFCP")
                vFCP.text = f"{line.icms_fcp_value:.2f}"

    elif cst == "10":
        # N03 - Tributada com cobrança de ICMS por ST
        icms10 = etree.SubElement(icms_root, "ICMS10")

        orig = etree.SubElement(icms10, "orig")
        orig.text = origin

        CST = etree.SubElement(icms10, "CST")
        CST.text = cst

        # N13 - Modalidade BC
        modBC = etree.SubElement(icms10, "modBC")
        modBC.text = line.icms_bc_modality or "3"

        # N15 - Valor BC
        vBC = etree.SubElement(icms10, "vBC")
        vBC.text = f"{line.icms_bc_value:.2f}"

        # N16 - Alíquota
        pICMS = etree.SubElement(icms10, "pICMS")
        pICMS.text = f"{line.icms_tax_percent:.2f}"

        # N17 - Valor ICMS
        vICMS = etree.SubElement(icms10, "vICMS")
        vICMS.text = f"{line.icms_value:.2f}"

        # N17b-d - FCP (opcional)
        if line.icms_fcp_bc_value:
            vBCFCP = etree.SubElement(icms10, "vBCFCP")
            vBCFCP.text = f"{line.icms_fcp_bc_value:.2f}"

            if line.icms_fcp_tax_percent:
                pFCP = etree.SubElement(icms10, "pFCP")
                pFCP.text = f"{line.icms_fcp_tax_percent:.2f}"

            if line.icms_fcp_value:
                vFCP = etree.SubElement(icms10, "vFCP")
                vFCP.text = f"{line.icms_fcp_value:.2f}"

        # N18 - Modalidade BC ST (obrigatório)
        modBCST = etree.SubElement(icms10, "modBCST")
        modBCST.text = line.icms_st_modality or "4"

        # N19 - MVA ST (opcional)
        if line.icms_st_mva_percent:
            pMVAST = etree.SubElement(icms10, "pMVAST")
            pMVAST.text = f"{line.icms_st_mva_percent:.4f}"

        # N20 - Redução BC ST (opcional)
        if line.icms_st_reduction_percent:
            pRedBCST = etree.SubElement(icms10, "pRedBCST")
            pRedBCST.text = f"{line.icms_st_reduction_percent:.4f}"

        # N21 - Valor BC ST (obrigatório)
        vBCST = etree.SubElement(icms10, "vBCST")
        vBCST.text = f"{line.icms_st_bc_value:.2f}"

        # N22 - Alíquota ICMS ST (obrigatório)
        pICMSST = etree.SubElement(icms10, "pICMSST")
        pICMSST.text = f"{line.icms_st_tax_percent:.2f}"

        # N23 - Valor ICMS ST (obrigatório)
        vICMSST = etree.SubElement(icms10, "vICMSST")
        vICMSST.text = f"{line.icms_st_value:.2f}"

        # N23a-c - FCP ST (opcional)
        if line.icms_st_fcp_bc_value:
            vBCFCPST = etree.SubElement(icms10, "vBCFCPST")
            vBCFCPST.text = f"{line.icms_st_fcp_bc_value:.2f}"

            if line.icms_st_fcp_tax_percent:
                pFCPST = etree.SubElement(icms10, "pFCPST")
                pFCPST.text = f"{line.icms_st_fcp_tax_percent:.2f}"

            if line.icms_st_fcp_value:
                vFCPST = etree.SubElement(icms10, "vFCPST")
                vFCPST.text = f"{line.icms_st_fcp_value:.2f}"

    elif cst == "20":
        # N04 - Com redução de BC
        icms20 = etree.SubElement(icms_root, "ICMS20")

        orig = etree.SubElement(icms20, "orig")
        orig.text = origin

        CST = etree.SubElement(icms20, "CST")
        CST.text = cst

        # N13 - Modalidade BC
        modBC = etree.SubElement(icms20, "modBC")
        modBC.text = line.icms_bc_modality or "3"

        # N14 - Percentual redução BC (obrigatório para CST 20)
        pRedBC = etree.SubElement(icms20, "pRedBC")
        pRedBC.text = f"{line.icms_bc_reduction_percent:.4f}"

        # N15 - Valor BC
        vBC = etree.SubElement(icms20, "vBC")
        vBC.text = f"{line.icms_bc_value:.2f}"

        # N16 - Alíquota
        pICMS = etree.SubElement(icms20, "pICMS")
        pICMS.text = f"{line.icms_tax_percent:.2f}"

        # N17 - Valor ICMS
        vICMS = etree.SubElement(icms20, "vICMS")
        vICMS.text = f"{line.icms_value:.2f}"

        # N17b-d - FCP (opcional)
        if line.icms_fcp_bc_value:
            vBCFCP = etree.SubElement(icms20, "vBCFCP")
            vBCFCP.text = f"{line.icms_fcp_bc_value:.2f}"

            if line.icms_fcp_tax_percent:
                pFCP = etree.SubElement(icms20, "pFCP")
                pFCP.text = f"{line.icms_fcp_tax_percent:.2f}"

            if line.icms_fcp_value:
                vFCP = etree.SubElement(icms20, "vFCP")
                vFCP.text = f"{line.icms_fcp_value:.2f}"

        # TODO: N27a - vICMSDeson (desoneração) - não implementado
        # TODO: N28 - motDesICMS (motivo desoneração) - não implementado

    elif cst == "30":
        # N05 - Isenta ou não tributada com cobrança de ICMS por ST
        icms30 = etree.SubElement(icms_root, "ICMS30")

        orig = etree.SubElement(icms30, "orig")
        orig.text = origin

        CST = etree.SubElement(icms30, "CST")
        CST.text = cst

        # N18 - Modalidade BC ST (obrigatório)
        modBCST = etree.SubElement(icms30, "modBCST")
        modBCST.text = line.icms_st_modality or "4"

        # N19 - MVA ST (opcional)
        if line.icms_st_mva_percent:
            pMVAST = etree.SubElement(icms30, "pMVAST")
            pMVAST.text = f"{line.icms_st_mva_percent:.4f}"

        # N20 - Redução BC ST (opcional)
        if line.icms_st_reduction_percent:
            pRedBCST = etree.SubElement(icms30, "pRedBCST")
            pRedBCST.text = f"{line.icms_st_reduction_percent:.4f}"

        # N21 - Valor BC ST (obrigatório)
        vBCST = etree.SubElement(icms30, "vBCST")
        vBCST.text = f"{line.icms_st_bc_value:.2f}"

        # N22 - Alíquota ICMS ST (obrigatório)
        pICMSST = etree.SubElement(icms30, "pICMSST")
        pICMSST.text = f"{line.icms_st_tax_percent:.2f}"

        # N23 - Valor ICMS ST (obrigatório)
        vICMSST = etree.SubElement(icms30, "vICMSST")
        vICMSST.text = f"{line.icms_st_value:.2f}"

        # N23a-c - FCP ST (opcional)
        if line.icms_st_fcp_bc_value:
            vBCFCPST = etree.SubElement(icms30, "vBCFCPST")
            vBCFCPST.text = f"{line.icms_st_fcp_bc_value:.2f}"

            if line.icms_st_fcp_tax_percent:
                pFCPST = etree.SubElement(icms30, "pFCPST")
                pFCPST.text = f"{line.icms_st_fcp_tax_percent:.2f}"

            if line.icms_st_fcp_value:
                vFCPST = etree.SubElement(icms30, "vFCPST")
                vFCPST.text = f"{line.icms_st_fcp_value:.2f}"

        # TODO: N27a - vICMSDeson (desoneração) - não implementado
        # TODO: N28 - motDesICMS (motivo desoneração) - não implementado

    elif cst in ("40", "41", "50"):
        # N06 - Isenta (40) / Não tributada (41) / Suspensão (50)
        icms40 = etree.SubElement(icms_root, "ICMS40")

        orig = etree.SubElement(icms40, "orig")
        orig.text = origin

        CST = etree.SubElement(icms40, "CST")
        CST.text = cst

        # TODO: N27a - vICMSDeson (desoneração) - não implementado
        # TODO: N28 - motDesICMS (motivo desoneração) - não implementado

    elif cst == "51":
        # N07 - Diferimento
        icms51 = etree.SubElement(icms_root, "ICMS51")

        orig = etree.SubElement(icms51, "orig")
        orig.text = origin

        CST = etree.SubElement(icms51, "CST")
        CST.text = cst

        # N13 - Modalidade BC (opcional para CST 51)
        if line.icms_bc_modality:
            modBC = etree.SubElement(icms51, "modBC")
            modBC.text = line.icms_bc_modality

        # N14 - Redução BC (opcional)
        if line.icms_bc_reduction_percent:
            pRedBC = etree.SubElement(icms51, "pRedBC")
            pRedBC.text = f"{line.icms_bc_reduction_percent:.4f}"

        # N15 - Valor BC (opcional)
        if line.icms_bc_value:
            vBC = etree.SubElement(icms51, "vBC")
            vBC.text = f"{line.icms_bc_value:.2f}"

        # N16 - Alíquota (opcional)
        if line.icms_tax_percent:
            pICMS = etree.SubElement(icms51, "pICMS")
            pICMS.text = f"{line.icms_tax_percent:.2f}"

        # N17 - Valor ICMS Operação (opcional)
        if line.icms_value:
            vICMSOp = etree.SubElement(icms51, "vICMSOp")
            vICMSOp.text = f"{line.icms_value:.2f}"

        # N26 - Percentual diferimento (obrigatório para CST 51)
        pDif = etree.SubElement(icms51, "pDif")
        pDif.text = f"{line.icms_deferment_percent:.4f}"

        # N27 - Valor ICMS diferido (obrigatório)
        vICMSDif = etree.SubElement(icms51, "vICMSDif")
        vICMSDif.text = f"{line.icms_deferment_value:.2f}"

        # N17 - Valor ICMS (calculado: vICMSOp - vICMSDif)
        if line.icms_value and line.icms_deferment_value:
            vICMS = etree.SubElement(icms51, "vICMS")
            vICMS.text = f"{(line.icms_value - line.icms_deferment_value):.2f}"

        # N17b-d - FCP (opcional)
        if line.icms_fcp_bc_value:
            vBCFCP = etree.SubElement(icms51, "vBCFCP")
            vBCFCP.text = f"{line.icms_fcp_bc_value:.2f}"

            if line.icms_fcp_tax_percent:
                pFCP = etree.SubElement(icms51, "pFCP")
                pFCP.text = f"{line.icms_fcp_tax_percent:.2f}"

            if line.icms_fcp_value:
                vFCP = etree.SubElement(icms51, "vFCP")
                vFCP.text = f"{line.icms_fcp_value:.2f}"

    elif cst == "60":
        # N08 - ICMS cobrado anteriormente por ST
        icms60 = etree.SubElement(icms_root, "ICMS60")

        orig = etree.SubElement(icms60, "orig")
        orig.text = origin

        CST = etree.SubElement(icms60, "CST")
        CST.text = cst

        # TODO: Campos específicos do CST 60 (não implementados)
        # N24 - vBCSTRet (BC do ICMS ST retido)
        # N25 - pST (Alíquota suportada pelo consumidor final)
        # N25a - vICMSSubstituto (Valor do ICMS Próprio do Substituto)
        # N26 - vICMSSTRet (Valor do ICMS ST retido)
        # N26a - vBCFCPSTRet (BC FCP retido por ST)
        # N26b - pFCPSTRet (% FCP retido por ST)
        # N26c - vFCPSTRet (Valor FCP retido por ST)
        # TODO: N27a - vICMSDeson
        # TODO: N28 - motDesICMS

    elif cst == "70":
        # N09 - Com redução de BC e cobrança de ICMS por ST
        icms70 = etree.SubElement(icms_root, "ICMS70")

        orig = etree.SubElement(icms70, "orig")
        orig.text = origin

        CST = etree.SubElement(icms70, "CST")
        CST.text = cst

        # N13 - Modalidade BC
        modBC = etree.SubElement(icms70, "modBC")
        modBC.text = line.icms_bc_modality or "3"

        # N14 - Percentual redução BC (obrigatório para CST 70)
        pRedBC = etree.SubElement(icms70, "pRedBC")
        pRedBC.text = f"{line.icms_bc_reduction_percent:.4f}"

        # N15 - Valor BC
        vBC = etree.SubElement(icms70, "vBC")
        vBC.text = f"{line.icms_bc_value:.2f}"

        # N16 - Alíquota
        pICMS = etree.SubElement(icms70, "pICMS")
        pICMS.text = f"{line.icms_tax_percent:.2f}"

        # N17 - Valor ICMS
        vICMS = etree.SubElement(icms70, "vICMS")
        vICMS.text = f"{line.icms_value:.2f}"

        # N17b-d - FCP (opcional)
        if line.icms_fcp_bc_value:
            vBCFCP = etree.SubElement(icms70, "vBCFCP")
            vBCFCP.text = f"{line.icms_fcp_bc_value:.2f}"

            if line.icms_fcp_tax_percent:
                pFCP = etree.SubElement(icms70, "pFCP")
                pFCP.text = f"{line.icms_fcp_tax_percent:.2f}"

            if line.icms_fcp_value:
                vFCP = etree.SubElement(icms70, "vFCP")
                vFCP.text = f"{line.icms_fcp_value:.2f}"

        # N18 - Modalidade BC ST (obrigatório)
        modBCST = etree.SubElement(icms70, "modBCST")
        modBCST.text = line.icms_st_modality or "4"

        # N19 - MVA ST (opcional)
        if line.icms_st_mva_percent:
            pMVAST = etree.SubElement(icms70, "pMVAST")
            pMVAST.text = f"{line.icms_st_mva_percent:.4f}"

        # N20 - Redução BC ST (opcional)
        if line.icms_st_reduction_percent:
            pRedBCST = etree.SubElement(icms70, "pRedBCST")
            pRedBCST.text = f"{line.icms_st_reduction_percent:.4f}"

        # N21 - Valor BC ST (obrigatório)
        vBCST = etree.SubElement(icms70, "vBCST")
        vBCST.text = f"{line.icms_st_bc_value:.2f}"

        # N22 - Alíquota ICMS ST (obrigatório)
        pICMSST = etree.SubElement(icms70, "pICMSST")
        pICMSST.text = f"{line.icms_st_tax_percent:.2f}"

        # N23 - Valor ICMS ST (obrigatório)
        vICMSST = etree.SubElement(icms70, "vICMSST")
        vICMSST.text = f"{line.icms_st_value:.2f}"

        # N23a-c - FCP ST (opcional)
        if line.icms_st_fcp_bc_value:
            vBCFCPST = etree.SubElement(icms70, "vBCFCPST")
            vBCFCPST.text = f"{line.icms_st_fcp_bc_value:.2f}"

            if line.icms_st_fcp_tax_percent:
                pFCPST = etree.SubElement(icms70, "pFCPST")
                pFCPST.text = f"{line.icms_st_fcp_tax_percent:.2f}"

            if line.icms_st_fcp_value:
                vFCPST = etree.SubElement(icms70, "vFCPST")
                vFCPST.text = f"{line.icms_st_fcp_value:.2f}"

        # TODO: N27a - vICMSDeson
        # TODO: N28 - motDesICMS

    elif cst == "90":
        # N10 - Outros
        icms90 = etree.SubElement(icms_root, "ICMS90")

        orig = etree.SubElement(icms90, "orig")
        orig.text = origin

        CST = etree.SubElement(icms90, "CST")
        CST.text = cst

        # Para CST 90, os campos são opcionais dependendo da situação
        if line.icms_bc_modality:
            modBC = etree.SubElement(icms90, "modBC")
            modBC.text = line.icms_bc_modality

        if line.icms_bc_value:
            vBC = etree.SubElement(icms90, "vBC")
            vBC.text = f"{line.icms_bc_value:.2f}"

        if line.icms_bc_reduction_percent:
            pRedBC = etree.SubElement(icms90, "pRedBC")
            pRedBC.text = f"{line.icms_bc_reduction_percent:.4f}"

        if line.icms_tax_percent:
            pICMS = etree.SubElement(icms90, "pICMS")
            pICMS.text = f"{line.icms_tax_percent:.2f}"

        if line.icms_value:
            vICMS = etree.SubElement(icms90, "vICMS")
            vICMS.text = f"{line.icms_value:.2f}"

        # FCP (opcional)
        if line.icms_fcp_bc_value:
            vBCFCP = etree.SubElement(icms90, "vBCFCP")
            vBCFCP.text = f"{line.icms_fcp_bc_value:.2f}"

            if line.icms_fcp_tax_percent:
                pFCP = etree.SubElement(icms90, "pFCP")
                pFCP.text = f"{line.icms_fcp_tax_percent:.2f}"

            if line.icms_fcp_value:
                vFCP = etree.SubElement(icms90, "vFCP")
                vFCP.text = f"{line.icms_fcp_value:.2f}"

        # ICMS ST (opcional)
        if line.icms_st_modality:
            modBCST = etree.SubElement(icms90, "modBCST")
            modBCST.text = line.icms_st_modality

        if line.icms_st_mva_percent:
            pMVAST = etree.SubElement(icms90, "pMVAST")
            pMVAST.text = f"{line.icms_st_mva_percent:.4f}"

        if line.icms_st_reduction_percent:
            pRedBCST = etree.SubElement(icms90, "pRedBCST")
            pRedBCST.text = f"{line.icms_st_reduction_percent:.4f}"

        if line.icms_st_bc_value:
            vBCST = etree.SubElement(icms90, "vBCST")
            vBCST.text = f"{line.icms_st_bc_value:.2f}"

        if line.icms_st_tax_percent:
            pICMSST = etree.SubElement(icms90, "pICMSST")
            pICMSST.text = f"{line.icms_st_tax_percent:.2f}"

        if line.icms_st_value:
            vICMSST = etree.SubElement(icms90, "vICMSST")
            vICMSST.text = f"{line.icms_st_value:.2f}"

        # FCP ST (opcional)
        if line.icms_st_fcp_bc_value:
            vBCFCPST = etree.SubElement(icms90, "vBCFCPST")
            vBCFCPST.text = f"{line.icms_st_fcp_bc_value:.2f}"

            if line.icms_st_fcp_tax_percent:
                pFCPST = etree.SubElement(icms90, "pFCPST")
                pFCPST.text = f"{line.icms_st_fcp_tax_percent:.2f}"

            if line.icms_st_fcp_value:
                vFCPST = etree.SubElement(icms90, "vFCPST")
                vFCPST.text = f"{line.icms_st_fcp_value:.2f}"

        # TODO: N27a - vICMSDeson
        # TODO: N28 - motDesICMS


def _buildICMSSN(icms_root, line, origin, csosn, is_final_customer):
    """Constrói XML ICMS para Simples Nacional (CSOSN) conforme Manual NFe 4.00"""

    if csosn == "101":
        # N10c - Tributada SN com permissão de crédito
        icmssn101 = etree.SubElement(icms_root, "ICMSSN101")

        # N11 - Origem
        orig = etree.SubElement(icmssn101, "orig")
        orig.text = origin

        # N12a - CSOSN
        CSOSN = etree.SubElement(icmssn101, "CSOSN")
        CSOSN.text = csosn

        # N29 - Alíquota de crédito (obrigatório)
        pCredSN = etree.SubElement(icmssn101, "pCredSN")
        pCredSN.text = f"{line.icms_sn_credit_percent:.4f}"

        # N30 - Valor de crédito (obrigatório)
        vCredICMSSN = etree.SubElement(icmssn101, "vCredICMSSN")
        vCredICMSSN.text = f"{line.icms_sn_credit_value:.2f}"

    elif csosn in ("102", "103", "300", "400"):
        # N10d - Tributada SN sem crédito (102, 103)
        # N10d - Imune (300) - exportacao de mercadorias
        # N10d - Não tributada SN (400)
        # - operações de remessa de um modo geral (remessa para industrialização por encomenda, remessa para utilização em prestação de serviço, remessa para locação, remessa para beneficiamento, remessa em comodato, remessa em demonstração, remessa para conserto);
        # - operações realizadas a título gratuito (amostras, bonificações, doações, brindes);
        # - operações de transferência de mercadorias entre matriz e filial mesmo que entre Unidades da Federação distintas;
        # - operações de transferência de propriedade (onde exista o sucessor e o sucedido).
        icmssn102 = etree.SubElement(icms_root, "ICMSSN102")

        orig = etree.SubElement(icmssn102, "orig")
        orig.text = origin

        CSOSN = etree.SubElement(icmssn102, "CSOSN")
        CSOSN.text = csosn

    elif csosn == "201":
        # N10e - Tributada SN com crédito e com cobrança de ICMS por ST
        icmssn201 = etree.SubElement(icms_root, "ICMSSN201")

        orig = etree.SubElement(icmssn201, "orig")
        orig.text = origin

        CSOSN = etree.SubElement(icmssn201, "CSOSN")
        CSOSN.text = csosn

        _buildICMSSNST(icmssn201, line)

        if not line.icms_sn_credit_percent or line.icms_sn_credit_percent <= 0:
            raise ValidationError(
                "Geração de XML: Aliquota de Crédito do ICMS SN é obrigatório pro CST SN 201."
            )

        # N29 - Alíquota de crédito (obrigatório)
        pCredSN = etree.SubElement(icmssn201, "pCredSN")
        pCredSN.text = f"{line.icms_sn_credit_percent:.4f}"

        if not line.icms_sn_credit_value or line.icms_sn_credit_value <= 0:
            raise ValidationError(
                "Geração de XML: Valor de Crédito do ICMS SN é obrigatório pro CST SN 201."
            )

        # N30 - Valor de crédito (obrigatório)
        vCredICMSSN = etree.SubElement(icmssn201, "vCredICMSSN")
        vCredICMSSN.text = f"{line.icms_sn_credit_value:.2f}"

    elif csosn in ("202", "203"):
        # N10f - Tributada SN sem crédito e com cobrança de ICMS por ST (202, 203)
        icmssn202 = etree.SubElement(icms_root, "ICMSSN202")

        orig = etree.SubElement(icmssn202, "orig")
        orig.text = origin

        CSOSN = etree.SubElement(icmssn202, "CSOSN")
        CSOSN.text = csosn

        _buildICMSSNST(icmssn202, line)

    elif csosn == "500":
        # N10h - ICMS cobrado anteriormente por ST (substituído) ou antecipação
        icmssn500 = etree.SubElement(icms_root, "ICMSSN500")

        orig = etree.SubElement(icmssn500, "orig")
        orig.text = origin

        CSOSN = etree.SubElement(icmssn500, "CSOSN")
        CSOSN.text = csosn

        if not is_final_customer:
            raise ValidationError(
                "TODO: Implementar CSOSN 500 para operação de consumidor final."
            )

        # TODO: Campos opcionais do CSOSN 500 (não implementados)
        # N24 - vBCSTRet (BC do ICMS ST retido)
        # N25 - pST (Alíquota suportada pelo consumidor final)
        # N26 - vICMSSTRet (Valor do ICMS ST retido)
        # N26a - vBCFCPSTRet (BC FCP retido por ST)
        # N26b - pFCPSTRet (% FCP retido por ST)
        # N26c - vFCPSTRet (Valor FCP retido por ST)

    elif csosn == "900":
        # N10i - Outros - ex: devolucao de mercadoria
        icmssn900 = etree.SubElement(icms_root, "ICMSSN900")

        orig = etree.SubElement(icmssn900, "orig")
        orig.text = origin

        CSOSN = etree.SubElement(icmssn900, "CSOSN")
        CSOSN.text = csosn

        icms_fields = [
            line.icms_bc_modality,
            line.icms_bc_value,
            line.icms_tax_percent,
            line.icms_value,
        ]
        if any(icms_fields) and not all(icms_fields):
            raise ValidationError(
                f"Geração de XML: (Produto: {line.product_description})"
                f"Para o CSOSN 900 se o grupo do ICMS for informado, é obrigatório "
                f"informar a modalidade da base de calculo, valor da base de calculo, "
                f"aliquota do ICMS e valor do ICMS. Validação referente ao item da nota "
                f"fiscal: {line.product_description}."
            )

        if line.icms_bc_modality:
            modBC = etree.SubElement(icmssn900, "modBC")
            modBC.text = line.icms_bc_modality

            vBC = etree.SubElement(icmssn900, "vBC")
            vBC.text = f"{line.icms_bc_value:.2f}"

            pICMS = etree.SubElement(icmssn900, "pICMS")
            pICMS.text = f"{line.icms_tax_percent:.2f}"

            vICMS = etree.SubElement(icmssn900, "vICMS")
            vICMS.text = f"{line.icms_value:.2f}"

        if line.icms_bc_reduction_percent:
            pRedBC = etree.SubElement(icmssn900, "pRedBC")
            pRedBC.text = f"{line.icms_bc_reduction_percent:.4f}"

        icms_st_fields = [
            line.icms_st_modality,
            line.icms_st_bc_value,
            line.icms_st_tax_percent,
            line.icms_st_value,
        ]
        if any(icms_st_fields) and not all(icms_st_fields):
            raise ValidationError(
                f"Geração de XML: (Produto: {line.product_description})"
                f"Para o CSOSN 900 se o grupo do ICMS ST for informado, é obrigatório "
                f"informar a modalidade da base de calculo ST, valor da base de calculo ST, "
                f"aliquota do ICMS ST e valor do ICMS ST. Validação referente ao item da nota "
                f"fiscal: {line.product_description}."
            )

        if line.icms_st_modality:
            modBCST = etree.SubElement(icmssn900, "modBCST")
            modBCST.text = line.icms_st_modality

            vBCST = etree.SubElement(icmssn900, "vBCST")
            vBCST.text = f"{line.icms_st_bc_value:.2f}"

            pICMSST = etree.SubElement(icmssn900, "pICMSST")
            pICMSST.text = f"{line.icms_st_tax_percent:.2f}"

            vICMSST = etree.SubElement(icmssn900, "vICMSST")
            vICMSST.text = f"{line.icms_st_value:.2f}"

        if line.icms_st_modality == "4" and not line.icms_st_mva_percent:
            raise ValidationError(
                f"Geração de XML: (Produto: {line.product_description})"
                f"MVA ICMS ST é obrigatório para a modalidade da Base de Calculo do ICMS ST Margem Valor Agregado (%)."
            )

        if line.icms_st_mva_percent:
            pMVAST = etree.SubElement(icmssn900, "pMVAST")
            pMVAST.text = f"{line.icms_st_mva_percent:.4f}"

        if line.icms_st_reduction_percent:
            pRedBCST = etree.SubElement(icmssn900, "pRedBCST")
            pRedBCST.text = f"{line.icms_st_reduction_percent:.4f}"

        icms_st_fcp_fields = [
            line.icms_st_fcp_bc_value,
            line.icms_st_fcp_tax_percent,
            line.icms_st_fcp_value,
        ]
        if any(icms_st_fcp_fields) and not all(icms_st_fcp_fields):
            raise ValidationError(
                f"Geração de XML: (Produto: {line.product_description})"
                f"Para o CSOSN 900 se o grupo do FCP ST for informado, é obrigatório informar "
                f"o valor da base de calculo do FCP ST, aliquota do FCP ST e valor do FCP ST."
            )

        if line.icms_st_fcp_bc_value:
            vBCFCPST = etree.SubElement(icmssn900, "vBCFCPST")
            vBCFCPST.text = f"{line.icms_st_fcp_bc_value:.2f}"

            pFCPST = etree.SubElement(icmssn900, "pFCPST")
            pFCPST.text = f"{line.icms_st_fcp_tax_percent:.4f}"

            vFCPST = etree.SubElement(icmssn900, "vFCPST")
            vFCPST.text = f"{line.icms_st_fcp_value:.2f}"

        icms_sn_credit_fields = [
            line.icms_sn_credit_percent,
            line.icms_sn_credit_value,
        ]
        if any(icms_sn_credit_fields) and not all(icms_sn_credit_fields):
            raise ValidationError(
                f"Geração de XML: (Produto: {line.product_description})"
                f"Para o CSOSN 900 se o grupo do ICMS SN for informado, é obrigatório "
                f"informar a aliquota de crédito do ICMS SN ou o valor do crédito do ICMS SN."
            )

        if line.icms_sn_credit_percent:
            pCredSN = etree.SubElement(icmssn900, "pCredSN")
            pCredSN.text = f"{line.icms_sn_credit_percent:.4f}"

            vCredICMSSN = etree.SubElement(icmssn900, "vCredICMSSN")
            vCredICMSSN.text = f"{line.icms_sn_credit_value:.2f}"


def _buildICMSSNST(icmssn_root, line):
    # N18 - Modalidade BC ST (obrigatório)
    if not line.icms_st_modality:
        raise ValidationError(
            f"Geração de XML: (Produto: {line.product_description}) Modalidade da Base de Calculo do ICMS ST é obrigatório pro CST SN 201."
        )
    modBCST = etree.SubElement(icmssn_root, "modBCST")
    modBCST.text = line.icms_st_modality

    # N19 - MVA ST (opcional)
    if line.icms_st_modality == "4" and not line.icms_st_mva_percent:
        raise ValidationError(
            f"Geração de XML: (Produto: {line.product_description}) MVA ICMS ST é obrigatório para a modalidade da Base de Calculo do ICMS ST Margem Valor Agregado (%)."
        )
    if line.icms_st_mva_percent:
        pMVAST = etree.SubElement(icmssn_root, "pMVAST")
        pMVAST.text = f"{line.icms_st_mva_percent:.4f}"

    # N20 - Redução BC ST (opcional)
    if line.icms_st_reduction_percent:
        pRedBCST = etree.SubElement(icmssn_root, "pRedBCST")
        pRedBCST.text = f"{line.icms_st_reduction_percent:.4f}"

    # N21 - Valor BC ST (obrigatório)
    if not line.icms_st_bc_value or line.icms_st_bc_value <= 0:
        raise ValidationError(
            f"Geração de XML: (Produto: {line.product_description}) Valor da Base de Calculo do ICMS ST é obrigatório pro CST SN 201."
        )
    vBCST = etree.SubElement(icmssn_root, "vBCST")
    vBCST.text = f"{line.icms_st_bc_value:.2f}"

    # N22 - Alíquota ICMS ST (obrigatório)
    if not line.icms_st_tax_percent or line.icms_st_tax_percent <= 0:
        raise ValidationError(
            f"Geração de XML: (Produto: {line.product_description}) Alíquota do ICMS ST é obrigatório pro CST SN 201."
        )
    pICMSST = etree.SubElement(icmssn_root, "pICMSST")
    pICMSST.text = f"{line.icms_st_tax_percent:.2f}"

    # N23 - Valor ICMS ST (obrigatório)
    if not line.icms_st_value or line.icms_st_value <= 0:
        raise ValidationError(
            f"Geração de XML: (Produto: {line.product_description}) Valor do ICMS ST é obrigatório pro CST SN 201."
        )
    vICMSST = etree.SubElement(icmssn_root, "vICMSST")
    vICMSST.text = f"{line.icms_st_value:.2f}"

    if not line.icms_st_fcp_bc_value or line.icms_st_fcp_bc_value <= 0:
        raise ValidationError(
            f"Geração de XML: (Produto: {line.product_description}) Valor da Base de Calculo do FCP ST é obrigatório pro CST SN 201."
        )

    vBCFCPST = etree.SubElement(icmssn_root, "vBCFCPST")
    vBCFCPST.text = f"{line.icms_st_fcp_bc_value:.2f}"

    if not line.icms_st_fcp_tax_percent or line.icms_st_fcp_tax_percent <= 0:
        raise ValidationError(
            f"Geração de XML: (Produto: {line.product_description}) Aliquota do FCP ST é obrigatório pro CST SN 201."
        )

    pFCPST = etree.SubElement(icmssn_root, "pFCPST")
    pFCPST.text = f"{line.icms_st_fcp_tax_percent:.2f}"

    if not line.icms_st_fcp_value or line.icms_st_fcp_value <= 0:
        raise ValidationError(
            f"Geração de XML: (Produto: {line.product_description}) Valor do FCP ST é obrigatório pro CST SN 201."
        )

    vFCPST = etree.SubElement(icmssn_root, "vFCPST")
    vFCPST.text = f"{line.icms_st_fcp_value:.2f}"


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
    issuer_formatted_phone = fields.Char(
        related="issuer_id.phone",
        string="Telefone Emitente",
    )

    issuer_phone = fields.Char(
        compute="_compute_issuer_phone",
        string="Telefone Emitente",
        store=True,
    )

    @api.depends("issuer_formatted_phone")
    def _compute_issuer_phone(self):
        for record in self:
            if record.issuer_formatted_phone:
                record.issuer_phone = "".join(
                    filter(str.isdigit, record.issuer_formatted_phone)
                )
            else:
                record.issuer_phone = False

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
        string="Regime Fiscal do Emitente",
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

    recipient_fiscal_framework = fields.Selection(
        related="recipient_id.fiscal_framework",
        string="Regime Fiscal do Destinatário",
        store=True,
        readonly=True,
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
    recipient_formatted_phone = fields.Char(
        related="recipient_id.phone",
        string="Telefone Destinatário",
    )

    recipient_phone = fields.Char(
        compute="_compute_recipient_phone",
        string="Telefone Destinatário",
        store=True,
    )

    @api.depends("recipient_formatted_phone")
    def _compute_recipient_phone(self):
        for record in self:
            if record.recipient_formatted_phone:
                record.recipient_phone = "".join(
                    filter(str.isdigit, record.recipient_formatted_phone)
                )
            else:
                record.recipient_phone = False

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
                                f"As pessoas autorizadas a acessar o XML da NF-e devem ter um CPF válido. Verifique o CPF da pessoa: {authorized_xml_access_id.name}."
                            )
                        )
                    if authorized_xml_access_id.company_type == "company" and (
                        not authorized_xml_access_id.vat
                        or len(authorized_xml_access_id.vat) != 14
                    ):
                        raise ValidationError(
                            _(
                                f"As empresas autorizadas a acessar  o XML da NF-e devem ter um CNPJ válido. Verifique o CNPJ da empresa: {authorized_xml_access_id.name}."
                            )
                        )

    # === Grupo H. Detalhamento de Produtos e Serviços da NF-e  ===
    # det - Detalhamento de Produtos e Serviços. Múltiplas ocorrências (máximo = 990).

    invoice_line_ids = fields.One2many(
        comodel_name="l10n_br_nfe.nfe.document.line",
        inverse_name="nfe_id",
        string="Itens da Nota Fiscal",
    )

    @api.constrains("invoice_line_ids")
    def _check_invoice_line_ids(self):
        for record in self:
            if len(record.invoice_line_ids) > 990:
                raise ValidationError(
                    _("O número máximo de itens da nota fiscal é 990.")
                )

    # === Grupo W. Total da NF-e  ===
    # total - Totais da NF-e

    # Totais do ICMS

    def _is_issuer_simples_nacional(self):
        return self.issuer_id.fiscal_framework in ("1", "2")

    # Base de Cálculo do ICMS.
    total_icms_base = fields.Float(
        string="BC do ICMS",
        digits=(13, 2),
        compute="_compute_total_icms_base",
        store=True,
    )

    @api.depends("issuer_id", "issuer_id.fiscal_framework", "invoice_line_ids")
    def _compute_total_icms_base(self):
        for record in self:
            total_icms_base = sum(record.invoice_line_ids.mapped("icms_bc_value"))
            if (
                record._is_issuer_simples_nacional()
                and record.emission_finality == "1"
                and not total_icms_base == 0.00
            ):
                raise ValidationError(
                    _(
                        "A soma da base de cálculo do ICMS deve ser zero para nota fiscal"
                        " normal emitida por empresa do Simples Nacional."
                    )
                )
            else:
                record.total_icms_base = total_icms_base

    total_icms = fields.Float(
        string="Valor Total do ICMS",
        digits=(13, 2),
        compute="_compute_total_icms",
        store=True,
    )

    @api.depends("issuer_id", "issuer_id.fiscal_framework", "invoice_line_ids")
    def _compute_total_icms(self):
        for record in self:
            total_icms = sum(record.invoice_line_ids.mapped("icms_value"))
            if (
                record._is_issuer_simples_nacional()
                and record.emission_finality == "1"
                and not total_icms == 0.00
            ):
                raise ValidationError(
                    _(
                        "A soma do valor do ICMS deve ser zero para nota fiscal"
                        " normal emitida por empresa do Simples Nacional."
                    )
                )
            else:
                record.total_icms = total_icms

    # Valor Total do ICMS.

    # soma do valor do icms desonerado dos items, nao implementado
    total_icms_deson = fields.Float(
        string="Valor ICMS Desonerado",
        digits=(13, 2),
        compute="_compute_total_icms_deson",
        store=True,
    )

    def _compute_total_icms_deson(self):
        for record in self:
            record.total_icms_deson = 0.00

    # Valor Total do ICMS desonerado.

    # == icms difal ==

    # Valor Total do Fundo de Combate à Pobreza da UF de Destino.
    total_fcp_uf_dest = fields.Float(
        string="Valor Total FCP da UF de Destino",
        digits=(13, 2),
        compute="_compute_total_fcp_uf_dest",
        store=True,
    )

    def _compute_total_fcp_uf_dest(self):
        for record in self:
            record.total_fcp_uf_dest = 0.00

    # Valor Total do ICMS da UF de Destino.
    total_icms_uf_dest = fields.Float(
        string="Valor Total do ICMS da UF de Destino",
        digits=(13, 2),
        compute="_compute_total_icms_uf_dest",
        store=True,
    )

    def _compute_total_icms_uf_dest(self):
        for record in self:
            record.total_icms_uf_dest = 0.00

    total_icms_interestadual = fields.Float(
        string="Valor Total do ICMS Interestadual",
        digits=(13, 2),
        compute="_compute_total_icms_interestadual",
        store=True,
    )

    def _compute_total_icms_interestadual(self):
        for record in self:
            record.total_icms_interestadual = 0.00

    # Valor Total do Fundo de Combate à Pobreza.
    total_fcp = fields.Float(
        string="Valor Total FCP",
        digits=(13, 2),
        compute="_compute_total_fcp",
        store=True,
    )

    @api.depends("issuer_id", "issuer_id.fiscal_framework", "invoice_line_ids")
    def _compute_total_fcp(self):
        for record in self:
            total_fcp = sum(record.invoice_line_ids.mapped("icms_fcp_value"))
            if (
                record._is_issuer_simples_nacional()
                and record.emission_finality == "1"
                and not total_fcp == 0.00
            ):
                raise ValidationError(
                    _(
                        "A soma do valor do FCP deve ser zero para nota fiscal"
                        " normal emitida por empresa do Simples Nacional."
                    )
                )
            else:
                record.total_fcp = total_fcp

    # Valor Total da Base de Calculo do ICMS ST.
    total_icms_st_base = fields.Float(
        string="Valor Total da Base de Calculo do ICMS ST",
        digits=(13, 2),
        compute="_compute_total_icms_st_base",
        store=True,
    )

    @api.depends("invoice_line_ids")
    def _compute_total_icms_st_base(self):
        for record in self:
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

    @api.depends("invoice_line_ids")
    def _compute_total_icms_st_value(self):
        for record in self:
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

    @api.depends("invoice_line_ids")
    def _compute_total_icms_st_fcp(self):
        for record in self:
            record.total_icms_st_fcp = sum(
                record.invoice_line_ids.mapped("icms_st_fcp_value")
            )

    # Valor Total do FCP ST Retido Anteriormente por Substituição Tributária.
    total_icms_fcp_st_retention = fields.Float(
        string="Valor Total do FCP ST Retido Anteriormente por Substituição Tributária",
        digits=(13, 2),
        compute="_compute_total_icms_fcp_st_retention",
        store=True,
    )

    @api.depends("invoice_line_ids")
    def _compute_total_icms_fcp_st_retention(self):
        for record in self:
            record.total_icms_fcp_st_retention = sum(
                record.invoice_line_ids.mapped("icms_st_fcp_retention_value")
            )

    # Valor Total dos Produtos e Serviços.
    total_products = fields.Float(
        string="Valor Total dos Produtos e Serviços",
        digits=(13, 2),
        store=True,
        compute="_compute_total_products",
    )

    @api.depends("invoice_line_ids")
    def _compute_total_products(self):
        for record in self:
            record.total_products = sum(record.invoice_line_ids.mapped("total_value"))

    # Valor Total do Frete.
    total_freight = fields.Float(
        string="Valor Total do Frete",
        digits=(13, 2),
        required=True,
    )

    @api.onchange("total_freight")
    def _onchange_total_freight(self):
        for record in self:
            record.distribute_total_value(record.total_freight, "freight_value")
        return

    def distribute_total_value(self, total_value_to_distribute, item_key):
        """Rateia o frete proporcionalmente entre os itens da nota fiscal."""
        if not self.invoice_line_ids:
            return

        total_value = total_value_to_distribute or 0.0

        # Se valor for zero, zera o valor de todos os itens
        if total_value == 0:
            for line in self.invoice_line_ids:
                line[item_key] = 0.0
            return

        # Calcula o valor total de todos os itens
        total_items_value = sum(line.total_value for line in self.invoice_line_ids)

        # Se não houver valor total, distribui igualmente
        if total_items_value == 0:
            value_per_item = round(total_value / len(self.invoice_line_ids), 2)
            accumulated = 0.0
            lines = list(self.invoice_line_ids)
            for line in lines[:-1]:
                line[item_key] = value_per_item
                accumulated += value_per_item
            # Último item recebe o resto para evitar diferença de arredondamento
            lines[-1][item_key] = round(total_value - accumulated, 2)
            return

        # Rateia proporcionalmente ao valor de cada item
        accumulated = 0.0
        lines = list(self.invoice_line_ids)
        for line in lines[:-1]:
            proportion = line.total_value / total_items_value
            line[item_key] = round(total_value * proportion, 2)
            accumulated += line[item_key]

        # Último item recebe o resto para garantir que não haja diferença
        lines[-1][item_key] = round(total_value - accumulated, 2)

    # Valor Total do Seguro.
    total_insurance = fields.Float(
        string="Valor Total do Seguro",
        digits=(13, 2),
        required=True,
    )

    @api.onchange("total_insurance")
    def _onchange_total_insurance(self):
        for record in self:
            record.distribute_total_value(record.total_insurance, "insurance_value")
        return

    # Valor Total do Desconto.
    total_discount = fields.Float(
        string="Valor Total do Desconto",
        digits=(13, 2),
        required=True,
    )

    @api.onchange("total_discount")
    def _onchange_total_discount(self):
        for record in self:
            record.distribute_total_value(record.total_discount, "discount_value")
        return

    @api.onchange("invoice_line_ids.discount_value")
    def _onchange_invoice_line_ids_discount_value(self):
        for record in self:
            record.total_discount = sum(
                record.invoice_line_ids.mapped("discount_value")
            )
        return

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
