from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError
from .utils import is_valid_phone, format_number
import random
import re
import pytz
from .constants import DESTINATION_ID, NFE_EMISSION_FINALITY
import lxml.etree as etree
from erpbrasil.assinatura.assinatura import Assinatura
from .nfe_xml_validator import validate_nfe_xml
import base64

NFE_NS = "http://www.portalfiscal.inf.br/nfe"

_INVALID_XML_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")


def sanitize_xml_text(text):
    """Remove invalid XML 1.0 characters (control chars except TAB, LF, CR).

    Standard entity escaping (&amp; &lt; &gt; &quot; &#39;) is handled
    automatically by lxml when the value is assigned to element.text.
    """
    if not text:
        return text
    return _INVALID_XML_CHARS_RE.sub("", text)


def sanitize_xml_tree(root):
    """Walk an entire lxml tree and sanitize every text node."""
    for elem in root.iter():
        if elem.text:
            elem.text = sanitize_xml_text(elem.text)
        if elem.tail:
            elem.tail = sanitize_xml_text(elem.tail)


def format_partner_address(street, number, complement, max_length=60):
    """
    Formata endereço abreviando o tipo de logradouro e limitando ao tamanho máximo.

    Args:
        street: Nome da rua/logradouro
        number: Número do endereço
        complement: Complemento do endereço
        max_length: Tamanho máximo da string (padrão 60)

    Returns:
        String formatada com no máximo max_length caracteres
    """
    if not street:
        return ""

    # Abreviações de tipos de logradouro brasileiro
    abbreviations = {
        "Avenida": "Av.",
        "Alameda": "Al.",
        "Beco": "Bc.",
        "Estrada": "Est.",
        "Largo": "Lg.",
        "Praça": "Pç.",
        "Quadra": "Qd.",
        "Rodovia": "Rod.",
        "Rua": "R.",
        "Travessa": "Tv.",
        "Via": "V.",
        "Viela": "Vl.",
    }

    # Aplica abreviação se o logradouro começar com um tipo conhecido
    abbreviated_street = street
    for full, abbr in abbreviations.items():
        if street.startswith(full + " "):
            abbreviated_street = abbr + street[len(full) :]
            break

    # Monta sufixo com número e complemento
    suffix_parts = []
    if number:
        suffix_parts.append(str(number))
    if complement:
        suffix_parts.append(str(complement))

    suffix = ", " + ", ".join(suffix_parts) if suffix_parts else ""

    # Calcula espaço disponível para o nome da rua
    available_for_street = max_length - len(suffix)

    # Trunca a rua se necessário
    if len(abbreviated_street) > available_for_street:
        abbreviated_street = (
            abbreviated_street[: available_for_street - 1].rstrip() + "."
        )

    return (abbreviated_street + suffix)[:max_length]


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
    # Ensure sequential item numbering before XML generation
    nfe_document.env["l10n_br_nfe.nfe.document.line"]._reorder_item_numbers(
        nfe_document.id
    )
    root = etree.Element("NFe")
    root.set("xmlns", NFE_NS)

    # grupo A
    infNFe = etree.SubElement(root, "infNFe")
    infNFe.set("versao", nfe_document.nfe_version)
    infNFe.set("Id", f"NFe{nfe_document.access_key}")

    # grupo B
    ide = etree.SubElement(infNFe, "ide")
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

    # nao se deve informar para NFC-e
    if nfe_document.document_model == "55" and nfe_document.departure_arrival_datetime:
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

    if len(nfe_document.ref_nfe_numbers) > 0:
        # grupo BA - Documento Fiscal Referenciado
        NFref = etree.SubElement(ide, "NFref")

        for ref_nfe_number in nfe_document.ref_nfe_numbers:
            refNFe = etree.SubElement(NFref, "refNFe")
            refNFe.text = ref_nfe_number.access_key

    # emitente
    emit = etree.SubElement(infNFe, "emit")

    if nfe_document.issuer_id.company_type == "company":
        CNPJ = etree.SubElement(emit, "CNPJ")
        CNPJ.text = nfe_document.issuer_cnpj
    else:
        CPF = etree.SubElement(emit, "CPF")
        CPF.text = nfe_document.issuer_cpf

    xNome = etree.SubElement(emit, "xNome")
    xNome.text = nfe_document.issuer_legal_name

    if nfe_document.issuer_trade_name:
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

    # grupo obrigatório para NF-e (modelo 55)
    if nfe_document.document_model == "55" and not nfe_document.recipient_id:
        raise ValidationError(
            _("Erro ao gerar XML: Para NF-e modelo 55, o Destinatário é obrigatório.")
        )

    if nfe_document.recipient_id:
        # Grupo E - Destinatário
        dest = etree.SubElement(infNFe, "dest")

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

        if nfe_document.recipient_street_complement:
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

        if nfe_document.recipient_zip:
            dCEP = etree.SubElement(dEnderDest, "CEP")
            dCEP.text = nfe_document.recipient_zip

        if nfe_document.recipient_id.is_foreign:
            if not nfe_document.recipient_id.country_id:
                raise ValidationError(
                    _(
                        "Erro ao gerar XML: O País do Destinatário é obrigatório para operações com exterior. Acesse o cadastro do destinatário e configure o país."
                    )
                )
            if not nfe_document.recipient_country_code:
                raise ValidationError(
                    _(
                        "Erro ao gerar XML: O Código do País do Destinatário é obrigatório para operações com exterior. Acesse o cadastro do destinatário e configure o país."
                    )
                )

            dCPais = etree.SubElement(dEnderDest, "cPais")
            dCPais.text = nfe_document.recipient_country_code

            dXpais = etree.SubElement(dEnderDest, "xPais")
            dXpais.text = nfe_document.recipient_country_name

        if nfe_document.recipient_phone:
            dFone = etree.SubElement(dEnderDest, "fone")
            dFone.text = nfe_document.recipient_phone

        indIEDest = etree.SubElement(dest, "indIEDest")
        indIEDest.text = nfe_document.recipient_ie_indicator

        if nfe_document.recipient_ie_indicator == "1":
            if not nfe_document.recipient_ie:
                raise ValidationError(
                    _(
                        "Erro ao gerar XML: A Inscrição Estadual do Destinatário é obrigatória."
                    )
                )
            dIE = etree.SubElement(dest, "IE")
            dIE.text = nfe_document.recipient_ie

        if nfe_document.recipient_suframa:
            dSuframa = etree.SubElement(dest, "Suframa")
            dSuframa.text = nfe_document.recipient_suframa

        if nfe_document.recipient_email:
            dEmail = etree.SubElement(dest, "email")
            dEmail.text = nfe_document.recipient_email

    if nfe_document.is_retrieval_location_different_from_issuer_address:
        if not nfe_document.retrieval_partner_id:
            raise ValidationError(
                _(
                    "Erro ao gerar XML: O Local de Retirada é obrigatório quando o local de retirada é diferente do endereço do emitente."
                )
            )
        retirada = etree.SubElement(infNFe, "retirada")

        if nfe_document.retrieval_partner_id.company_type == "company":
            rCNPJ = etree.SubElement(retirada, "CNPJ")
            rCNPJ.text = nfe_document.retrieval_cnpj
        else:
            rCPF = etree.SubElement(retirada, "CPF")
            rCPF.text = nfe_document.retrieval_cpf

        rXNome = etree.SubElement(retirada, "xNome")
        rXNome.text = nfe_document.retrieval_legal_name

        rXLgr = etree.SubElement(retirada, "xLgr")
        rXLgr.text = nfe_document.retrieval_street

        rNro = etree.SubElement(retirada, "nro")
        rNro.text = nfe_document.retrieval_street_number

        if nfe_document.retrieval_street_complement:
            rXCpl = etree.SubElement(retirada, "xCpl")
            rXCpl.text = nfe_document.retrieval_street_complement

        rXBairro = etree.SubElement(retirada, "xBairro")
        rXBairro.text = nfe_document.retrieval_district

        rCMun = etree.SubElement(retirada, "cMun")
        rCMun.text = nfe_document.retrieval_city_code

        rXMun = etree.SubElement(retirada, "xMun")
        rXMun.text = nfe_document.retrieval_city_name

        rUF = etree.SubElement(retirada, "UF")
        rUF.text = nfe_document.retrieval_state

        if nfe_document.retrieval_zip:
            rCEP = etree.SubElement(retirada, "CEP")
            rCEP.text = nfe_document.retrieval_zip

        if nfe_document.retrieval_country_code and nfe_document.retrieval_country_name:
            rCPais = etree.SubElement(retirada, "cPais")
            rCPais.text = nfe_document.retrieval_country_code

            rXpais = etree.SubElement(retirada, "xPais")
            rXpais.text = nfe_document.retrieval_country_name

        if nfe_document.retrieval_phone:
            rFone = etree.SubElement(retirada, "fone")
            rFone.text = nfe_document.retrieval_phone

        if nfe_document.retrieval_email:
            rEmail = etree.SubElement(retirada, "email")
            rEmail.text = nfe_document.retrieval_email

        if nfe_document.retrieval_ie:
            rIE = etree.SubElement(retirada, "IE")
            rIE.text = nfe_document.retrieval_ie

    if nfe_document.is_delivery_location_different_from_recipient_address:
        if not nfe_document.delivery_partner_id:
            raise ValidationError(
                _(
                    "Erro ao gerar XML: O Local de Entrega é obrigatório quando o local de entrega é diferente do endereço do destinatário."
                )
            )
        entrega = etree.SubElement(infNFe, "entrega")

        if nfe_document.delivery_partner_id.company_type == "company":
            dCNPJ = etree.SubElement(entrega, "CNPJ")
            dCNPJ.text = nfe_document.delivery_cnpj
        else:
            dCPF = etree.SubElement(entrega, "CPF")
            dCPF.text = nfe_document.delivery_cpf

        dXNome = etree.SubElement(entrega, "xNome")
        dXNome.text = nfe_document.delivery_legal_name

        dXLgr = etree.SubElement(entrega, "xLgr")
        dXLgr.text = nfe_document.delivery_street

        dNro = etree.SubElement(entrega, "nro")
        dNro.text = nfe_document.delivery_street_number

        if nfe_document.delivery_street_complement:
            dXCpl = etree.SubElement(entrega, "xCpl")
            dXCpl.text = nfe_document.delivery_street_complement

        dXBairro = etree.SubElement(entrega, "xBairro")
        dXBairro.text = nfe_document.delivery_district

        dCMun = etree.SubElement(entrega, "cMun")
        dCMun.text = nfe_document.delivery_city_code

        dXMun = etree.SubElement(entrega, "xMun")
        dXMun.text = nfe_document.delivery_city_name

        dUF = etree.SubElement(entrega, "UF")
        dUF.text = nfe_document.delivery_state

        if nfe_document.delivery_zip:
            dCEP = etree.SubElement(entrega, "CEP")
            dCEP.text = nfe_document.delivery_zip

        if nfe_document.delivery_country_code and nfe_document.delivery_country_name:
            dCPais = etree.SubElement(entrega, "cPais")
            dCPais.text = nfe_document.delivery_country_code

            dXpais = etree.SubElement(entrega, "xPais")
            dXpais.text = nfe_document.delivery_country_name

        if nfe_document.delivery_phone:
            dFone = etree.SubElement(entrega, "fone")
            dFone.text = nfe_document.delivery_phone

        if nfe_document.delivery_email:
            dEmail = etree.SubElement(entrega, "email")
            dEmail.text = nfe_document.delivery_email

        if nfe_document.delivery_ie:
            dIE = etree.SubElement(entrega, "IE")
            dIE.text = nfe_document.delivery_ie

    if nfe_document.authorized_xml_access_ids:
        autXML = etree.SubElement(infNFe, "autXML")
        for authorized_xml_access_id in nfe_document.authorized_xml_access_ids:
            if authorized_xml_access_id.company_type == "company":
                if (
                    not authorized_xml_access_id.vat
                    or len(authorized_xml_access_id.vat) != 14
                ):
                    raise ValidationError(
                        _(
                            f"Geração de XML: As empresas autorizadas a acessar o XML da NF-e devem ter um CNPJ válido. Verifique o CNPJ da empresa: {authorized_xml_access_id.name}."
                        )
                    )
                autXMLCNPJ = etree.SubElement(autXML, "CNPJ")
                autXMLCNPJ.text = authorized_xml_access_id.vat
            elif authorized_xml_access_id.company_type == "person":
                if (
                    not authorized_xml_access_id.vat
                    or len(authorized_xml_access_id.vat) != 11
                    or not authorized_xml_access_id.vat.isdigit()
                ):
                    raise ValidationError(
                        _(
                            f"Geração de XML: As pessoas autorizadas a acessar o XML da NF-e devem ter um CPF válido. Verifique o CPF da pessoa: {authorized_xml_access_id.name}."
                        )
                    )
                autXMLCPF = etree.SubElement(autXML, "CPF")
                autXMLCPF.text = authorized_xml_access_id.vat

    for item in nfe_document.invoice_line_ids:
        det = etree.SubElement(infNFe, "det")
        det.set("nItem", str(item.item_number))

        prod = etree.SubElement(det, "prod")

        cProd = etree.SubElement(prod, "cProd")
        cProd.text = item.product_code

        cEAN = etree.SubElement(prod, "cEAN")
        cEAN.text = item.gtin

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
        vUnCom.text = f"{item.unit_price:.2f}"

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

        buildICMS(imposto, item, nfe_document.final_customer_operation == "1")
        buildIPI(imposto, item)

        buildPIS(imposto, item)
        buildCOFINS(imposto, item)

        # TODO build Pis Confins ST

        # buildIPIReturned(imposto, item)

        if item.additional_information:
            additional_information = etree.SubElement(det, "infAdProd")
            additional_information.text = item.additional_information

    # grupo W - Total da NF-e
    buildTotal(infNFe, nfe_document)

    # grupo X - Informações do Transporte da NF-e
    buildTransp(infNFe, nfe_document)

    buildBilling(infNFe, nfe_document)

    buildPayment(infNFe, nfe_document)

    buildIntermediator(infNFe, nfe_document)

    buildAdditionalInformation(infNFe, nfe_document)

    buildTechContact(infNFe, nfe_document)

    sanitize_xml_tree(root)

    return root


def buildTotal(infNFe, nfe_document):
    # grupo W01 - Total da NF-e
    total = etree.SubElement(infNFe, "total")

    # grupo W02 - Totais referentes ao ICMS
    ICMSTot = etree.SubElement(total, "ICMSTot")

    # W03 - Base de Cálculo do ICMS
    vBC = etree.SubElement(ICMSTot, "vBC")
    vBC.text = f"{nfe_document.total_icms_base:.2f}"

    # W04 - Valor Total do ICMS
    vICMS = etree.SubElement(ICMSTot, "vICMS")
    vICMS.text = f"{nfe_document.total_icms:.2f}"

    # W04a - Valor Total do ICMS Desonerado (0-1)
    vICMSDeson = etree.SubElement(ICMSTot, "vICMSDeson")
    vICMSDeson.text = f"{nfe_document.total_icms_deson:.2f}"

    # W04c - Valor total do ICMS relativo ao FCP da UF de destino (0-1)
    if nfe_document.total_fcp_uf_dest:
        vFCPUFDest = etree.SubElement(ICMSTot, "vFCPUFDest")
        vFCPUFDest.text = f"{nfe_document.total_fcp_uf_dest:.2f}"

    # W04e - Valor total do ICMS Interestadual para a UF de destino (0-1)
    if nfe_document.total_icms_uf_dest:
        vICMSUFDest = etree.SubElement(ICMSTot, "vICMSUFDest")
        vICMSUFDest.text = f"{nfe_document.total_icms_uf_dest:.2f}"

    # W04g - Valor total do ICMS Interestadual para a UF do remetente (0-1)
    if nfe_document.total_icms_interestadual:
        vICMSUFRemet = etree.SubElement(ICMSTot, "vICMSUFRemet")
        vICMSUFRemet.text = f"{nfe_document.total_icms_interestadual:.2f}"

    # W04h - Valor Total do FCP
    vFCP = etree.SubElement(ICMSTot, "vFCP")
    vFCP.text = f"{nfe_document.total_fcp:.2f}"

    # W05 - Base de Cálculo do ICMS ST
    vBCST = etree.SubElement(ICMSTot, "vBCST")
    vBCST.text = f"{nfe_document.total_icms_st_base:.2f}"

    # W06 - Valor Total do ICMS ST
    vST = etree.SubElement(ICMSTot, "vST")
    vST.text = f"{nfe_document.total_icms_st_value:.2f}"

    # W06a - Valor Total do FCP retido por Substituição Tributária
    vFCPST = etree.SubElement(ICMSTot, "vFCPST")
    vFCPST.text = f"{nfe_document.total_icms_st_fcp:.2f}"

    # W06b - Valor Total do FCP retido anteriormente por Substituição Tributária
    vFCPSTRet = etree.SubElement(ICMSTot, "vFCPSTRet")
    vFCPSTRet.text = f"{nfe_document.total_icms_fcp_st_retention:.2f}"

    # W07 - Valor Total dos Produtos e Serviços
    vProd = etree.SubElement(ICMSTot, "vProd")
    vProd.text = f"{nfe_document.total_products:.2f}"

    # W08 - Valor Total do Frete
    vFrete = etree.SubElement(ICMSTot, "vFrete")
    vFrete.text = f"{nfe_document.total_freight:.2f}"

    # W09 - Valor Total do Seguro
    vSeg = etree.SubElement(ICMSTot, "vSeg")
    vSeg.text = f"{nfe_document.total_insurance:.2f}"

    # W10 - Valor Total do Desconto
    vDesc = etree.SubElement(ICMSTot, "vDesc")
    vDesc.text = f"{nfe_document.total_discount:.2f}"

    # W11 - Valor Total do II
    vII = etree.SubElement(ICMSTot, "vII")
    vII.text = f"{nfe_document.total_ii:.2f}"

    # W12 - Valor Total do IPI
    vIPI = etree.SubElement(ICMSTot, "vIPI")
    vIPI.text = f"{nfe_document.total_ipi:.2f}"

    # W12a - Valor Total do IPI devolvido (0-1) - apenas para finNFe=4 (devolução)
    vIPIDevol = etree.SubElement(ICMSTot, "vIPIDevol")
    if nfe_document.total_ipi_returned and nfe_document.emission_finality == "4":
        vIPIDevol.text = f"{nfe_document.total_ipi_returned:.2f}"
    else:
        vIPIDevol.text = "0.00"

    # W13 - Valor do PIS
    vPIS = etree.SubElement(ICMSTot, "vPIS")
    vPIS.text = f"{nfe_document.total_pis:.2f}"

    # W14 - Valor da COFINS
    vCOFINS = etree.SubElement(ICMSTot, "vCOFINS")
    vCOFINS.text = f"{nfe_document.total_cofins:.2f}"

    # W15 - Outras Despesas Acessórias
    vOutro = etree.SubElement(ICMSTot, "vOutro")
    vOutro.text = f"{nfe_document.total_other_expenses:.2f}"

    # W16 - Valor Total da NF-e
    vNF = etree.SubElement(ICMSTot, "vNF")
    vNF.text = f"{nfe_document.total_nfe:.2f}"

    # W16a - Valor aproximado total de tributos federais, estaduais e municipais (0-1)
    if nfe_document.total_approx_taxes:
        vTotTrib = etree.SubElement(ICMSTot, "vTotTrib")
        vTotTrib.text = f"{nfe_document.total_approx_taxes:.2f}"


def buildTransp(infNFe, nfe_document):
    # grupo X01 - Informações do Transporte da NF-e
    transp = etree.SubElement(infNFe, "transp")

    # X02 - Modalidade do Frete
    modFrete = etree.SubElement(transp, "modFrete")
    modFrete.text = nfe_document.freight_modality

    if nfe_document.freight_modality != "9":
        transporta = etree.SubElement(transp, "transporta")

        if not nfe_document.freight_partner_id.is_foreign:
            # X04 - CNPJ do Transportador (CE com X05)
            if nfe_document.freight_carrier_cnpj:
                CNPJ = etree.SubElement(transporta, "CNPJ")
                CNPJ.text = nfe_document.freight_carrier_cnpj
            # X05 - CPF do Transportador (CE com X04)
            elif nfe_document.freight_carrier_cpf:
                CPF = etree.SubElement(transporta, "CPF")
                CPF.text = nfe_document.freight_carrier_cpf

        # X06 - Razão Social ou nome (0-1)
        if nfe_document.freight_carrier_legal_name:
            xNome = etree.SubElement(transporta, "xNome")
            xNome.text = nfe_document.freight_carrier_legal_name

        # X07 - Inscrição Estadual do Transportador (0-1)
        if nfe_document.freight_carrier_ie:
            IE = etree.SubElement(transporta, "IE")
            IE.text = nfe_document.freight_carrier_ie

        # X08 - Endereço Completo (0-1)
        if nfe_document.freight_carrier_address:
            xEnder = etree.SubElement(transporta, "xEnder")
            xEnder.text = nfe_document.freight_carrier_address

        # X09 - Nome do Município (0-1)
        if nfe_document.freight_carrier_city_name:
            xMun = etree.SubElement(transporta, "xMun")
            xMun.text = nfe_document.freight_carrier_city_name

        # X10 - Sigla da UF (0-1)
        if nfe_document.freight_carrier_state:
            UF = etree.SubElement(transporta, "UF")
            if nfe_document.freight_partner_id.is_foreign:
                UF.text = "EX"
            else:
                UF.text = nfe_document.freight_carrier_state

        # X11 - Grupo Retenção ICMS transporte (0-1)
        # TODO: adicionar campos ret_transp_vserv, ret_transp_vbcret,
        #       ret_transp_picmsret, ret_transp_vicmsret, ret_transp_cfop,
        #       ret_transp_cmunfg ao modelo para habilitar este bloco.

        # X17.1 / X18 - Grupo Veículo de Transporte (0-1)
        if nfe_document.freight_carrier_vehicle_license_plate:
            veicTransp = etree.SubElement(transp, "veicTransp")

            # X19 - Placa do Veículo
            placa = etree.SubElement(veicTransp, "placa")
            placa.text = nfe_document.freight_carrier_vehicle_license_plate

            # X20 - Sigla da UF
            UF = etree.SubElement(veicTransp, "UF")
            if nfe_document.freight_partner_id.is_foreign:
                UF.text = "EX"
            else:
                UF.text = nfe_document.freight_carrier_vehicle_licence_plate_state_code

            # X21 - RNTC (0-1)
            if nfe_document.freight_carrier_vehicle_rntrc:
                RNTC = etree.SubElement(veicTransp, "RNTC")
                RNTC.text = nfe_document.freight_carrier_vehicle_rntrc

        # X22 - Grupo Reboque (0-5)
        for trailer in nfe_document.freight_carrier_trailers_ids:
            if not trailer.freight_carrier_vehicle_license_plate:
                continue

            reboque = etree.SubElement(transp, "reboque")

            # X23 - Placa do Veículo
            placa = etree.SubElement(reboque, "placa")
            placa.text = trailer.freight_carrier_vehicle_license_plate

            # X24 - Sigla da UF
            UF = etree.SubElement(reboque, "UF")
            if nfe_document.freight_partner_id.is_foreign:
                UF.text = "EX"
            else:
                UF.text = trailer.freight_carrier_vehicle_licence_plate_state_code

            # X25 - RNTC (0-1)
            if trailer.freight_carrier_vehicle_rntrc:
                RNTC = etree.SubElement(reboque, "RNTC")
                RNTC.text = trailer.freight_carrier_vehicle_rntrc

            # X25a - Identificação do Vagão (0-1)
            if trailer.freight_carrier_vehicle_wagon_identification:
                vagao = etree.SubElement(reboque, "vagao")
                vagao.text = trailer.freight_carrier_vehicle_wagon_identification

            # X25b - Identificação da Balsa (0-1)
            if trailer.freight_carrier_vehicle_barge_identification:
                balsa = etree.SubElement(reboque, "balsa")
                balsa.text = trailer.freight_carrier_vehicle_barge_identification

        # X26 - Grupo Volumes (0-5000)
        for volume in nfe_document.carrier_volume_ids:
            vol = etree.SubElement(transp, "vol")

            # X27 - Quantidade de volumes (0-1)
            if volume.quantity:
                qVol = etree.SubElement(vol, "qVol")
                qVol.text = str(volume.quantity)

            # X28 - Espécie dos volumes (0-1)
            if volume.species:
                esp = etree.SubElement(vol, "esp")
                esp.text = volume.species

            # X29 - Marca dos volumes (0-1)
            if volume.brand:
                marca = etree.SubElement(vol, "marca")
                marca.text = volume.brand

            # X30 - Numeração dos volumes (0-1)
            if volume.numbering:
                nVol = etree.SubElement(vol, "nVol")
                nVol.text = volume.numbering

            # X31 - Peso Líquido em kg (0-1)
            if volume.net_weight:
                pesoL = etree.SubElement(vol, "pesoL")
                pesoL.text = f"{volume.net_weight:.3f}"

            # X32 - Peso Bruto em kg (0-1)
            if volume.gross_weight:
                pesoB = etree.SubElement(vol, "pesoB")
                pesoB.text = f"{volume.gross_weight:.3f}"

            # X33 - Grupo Lacres (0-5000)
            for lacre in volume.lacre_ids:
                lacres = etree.SubElement(vol, "lacres")
                # X34 - Número do Lacre
                nLacre = etree.SubElement(lacres, "nLacre")
                nLacre.text = lacre.number


def buildBilling(infNFe, nfe_document):
    # grupo Y01 - Dados da Cobrança (0-1)
    has_fat = bool(nfe_document.billing_number)
    has_dup = bool(nfe_document.billing_installment_ids)

    if not has_fat and not has_dup:
        return

    cobr = etree.SubElement(infNFe, "cobr")

    # grupo Y02 - Dados da Fatura (0-1)
    if has_fat:
        fat = etree.SubElement(cobr, "fat")

        # Y03 - Número da Fatura (0-1)
        if nfe_document.billing_number:
            nFat = etree.SubElement(fat, "nFat")
            nFat.text = nfe_document.billing_number

        # Y04 - Valor Original da Fatura (0-1)
        if nfe_document.billing_original_value:
            vOrig = etree.SubElement(fat, "vOrig")
            vOrig.text = f"{nfe_document.billing_original_value:.2f}"

        # Y05 - Valor do Desconto da Fatura (0-1)
        if nfe_document.billing_discount_value:
            vDesc = etree.SubElement(fat, "vDesc")
            vDesc.text = f"{nfe_document.billing_discount_value:.2f}"

        # Y06 - Valor Líquido da Fatura (0-1)
        if nfe_document.billing_liquid_value:
            vLiq = etree.SubElement(fat, "vLiq")
            vLiq.text = f"{nfe_document.billing_liquid_value:.2f}"

    # grupo Y07 - Duplicatas / Parcelas (0-120)
    for installment in nfe_document.billing_installment_ids:
        dup = etree.SubElement(cobr, "dup")

        # Y08 - Número da Parcela (0-1)
        if installment.installment_number:
            nDup = etree.SubElement(dup, "nDup")
            nDup.text = installment.installment_number

        # Y09 - Data de Vencimento (0-1)
        if installment.due_date:
            dVenc = etree.SubElement(dup, "dVenc")
            dVenc.text = str(installment.due_date)

        # Y10 - Valor da Parcela (1-1)
        vDup = etree.SubElement(dup, "vDup")
        vDup.text = f"{installment.value:.2f}"


def buildPayment(infNFe, nfe_document):
    # grupo YA01 - Grupo de Informações de Pagamento (1-1)
    pag = etree.SubElement(infNFe, "pag")

    # grupo YA01a - Grupo Detalhamento do Pagamento (1-100)
    for payment in nfe_document.payment_detail_ids:
        detPag = etree.SubElement(pag, "detPag")

        # YA01b - Indicador da Forma de Pagamento (0-1)
        if payment.type:
            indPag = etree.SubElement(detPag, "indPag")
            indPag.text = payment.type

        # YA02 - Meio de pagamento (1-1)
        tPag = etree.SubElement(detPag, "tPag")
        tPag.text = payment.payment_method

        # YA03 - Valor do Pagamento (1-1)
        vPag = etree.SubElement(detPag, "vPag")
        vPag.text = f"{payment.payment_value:.2f}"

        # grupo YA04 - Grupo de Cartões (0-1)
        if payment.is_card_payment:
            card = etree.SubElement(detPag, "card")

            # YA04a - Tipo de Integração para pagamento (1-1)
            tpIntegra = etree.SubElement(card, "tpIntegra")
            tpIntegra.text = payment.card_integration_type

            # YA05 - CNPJ da instituição de pagamento (0-1)
            if payment.card_processor_cnpj:
                CNPJ = etree.SubElement(card, "CNPJ")
                CNPJ.text = payment.card_processor_cnpj

            # YA06 - Bandeira da operadora de cartão (0-1)
            if payment.card_brand:
                tBand = etree.SubElement(card, "tBand")
                tBand.text = payment.card_brand

            # YA07 - Número de autorização da operação cartão (0-1)
            if payment.card_authorization_number:
                cAut = etree.SubElement(card, "cAut")
                cAut.text = payment.card_authorization_number

    # YA09 - Valor do troco (0-1)
    total_change = sum(nfe_document.payment_detail_ids.mapped("change_value"))
    if total_change:
        vTroco = etree.SubElement(pag, "vTroco")
        vTroco.text = f"{total_change:.2f}"


def buildIntermediator(infNFe, nfe_document):
    # grupo YB - Informações do Intermediador da Transação (0-1)
    # Obrigatório quando intermediator_indicator = "1" (operação com intermediador/marketplace)
    if nfe_document.intermediator_indicator != "1":
        return

    infIntermed = etree.SubElement(infNFe, "infIntermed")

    # YB02 - CNPJ do Intermediador da Transação (1-1)
    CNPJ = etree.SubElement(infIntermed, "CNPJ")
    CNPJ.text = nfe_document.marketplace_cnpj

    # YB03 - Identificador cadastrado no intermediador (1-1)
    idCadIntTran = etree.SubElement(infIntermed, "idCadIntTran")
    idCadIntTran.text = nfe_document.marketplace_username


def removeDoubleSpaces(text):
    text = re.sub(r"[\r\n\t]+", " ", text)
    text = re.sub(r" {2,}", " ", text)
    return text.strip()


def buildAdditionalInformation(infNFe, nfe_document):
    # grupo Z - Informações Adicionais da NF-e (0-1)

    # Z03 - infCpl: combinação de informações obrigatórias + informações do emitente
    inf_fisco_parts = list(
        filter(
            None,
            [
                nfe_document.mandatory_additional_information,
                nfe_document.issuer_additional_information,
            ],
        )
    )
    inf_fisco = "\n".join(inf_fisco_parts) if inf_fisco_parts else None

    inf_issuer = nfe_document.issuer_additional_information or None

    if not inf_fisco and not inf_issuer:
        return
    else:
        if inf_fisco and len(inf_fisco) > 2000:
            raise ValidationError(
                "O tamanho máximo de informações adicionais de interesse do fisco é de 2000 caracteres."
            )
        if inf_issuer and len(inf_issuer) > 5000:
            raise ValidationError(
                "O tamanho máximo de informações adicionais do emitente é de 5000 caracteres."
            )

    infAdic = etree.SubElement(infNFe, "infAdic")

    # Z02 - Informações Adicionais de Interesse do Fisco (0-1, 1-2000)
    if inf_fisco:
        infAdFisco = etree.SubElement(infAdic, "infAdFisco")
        infAdFisco.text = removeDoubleSpaces(inf_fisco)

    if inf_issuer:
        infCpl = etree.SubElement(infAdic, "infCpl")
        infCpl.text = removeDoubleSpaces(inf_issuer)

    # Z04 - obsCont: Grupo Campo de uso livre do contribuinte (0-10)
    # Não há campos no modelo atualmente para obsCont

    # Z07 - obsFisco: Grupo Campo de uso livre do Fisco (0-10)
    # Não há campos no modelo atualmente para obsFisco

    # Z10 - procRef: Grupo Processo referenciado (0-100)
    # Não há campos no modelo atualmente para procRef


def buildTechContact(infNFe, nfe_document):
    # grupo ZD01 - Informações do Responsável Técnico pela emissão do DF-e (0-1)
    tech = nfe_document.tech_contact_id

    if not tech:
        return

    infRespTec = etree.SubElement(infNFe, "infRespTec")

    # ZD02 - CNPJ da pessoa jurídica responsável (1-1, N, 14)
    CNPJ = etree.SubElement(infRespTec, "CNPJ")
    CNPJ.text = nfe_document.tech_contact_cnpj

    # ZD04 - Nome da pessoa a ser contatada (1-1, C, 2-60)
    xContato = etree.SubElement(infRespTec, "xContato")
    xContato.text = nfe_document.tech_contact_name

    # ZD05 - E-mail da pessoa jurídica a ser contatada (1-1, C, 6-60)
    email = etree.SubElement(infRespTec, "email")
    email.text = nfe_document.tech_contact_email

    # ZD06 - Telefone da pessoa jurídica/física a ser contatada (1-1, N, 6-14)
    fone = etree.SubElement(infRespTec, "fone")
    fone.text = nfe_document.tech_contact_phone

    if tech.csrt_identifier and tech.csrt_hash:
        # ZD08 - Identificador do CSRT (N, 2)
        idCSRT = etree.SubElement(infRespTec, "idCSRT")
        idCSRT.text = tech.csrt_identifier

        # ZD09 - Hash SHA-1 Base64 do CSRT + chave de acesso (C, 28)
        hashCSRT = etree.SubElement(infRespTec, "hashCSRT")
        hashCSRT.text = tech.csrt_hash


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
    emission_finality = line.nfe_id.emission_finality

    if issuer_fiscal_framework in ("1", "2") and emission_finality in ("1", "2"):
        if not line.product_id.fiscal_type_id.code in ("04"):
            # se não for um produto fabricado, o grupo IPI não é informado
            return

        ipi = etree.SubElement(root, "IPI")

        cEnq = etree.SubElement(ipi, "cEnq")
        cEnq.text = "999"

        if line.ipi_cst == "99":
            IPITrib = etree.SubElement(ipi, "IPITrib")
            CST = etree.SubElement(IPITrib, "CST")
            CST.text = line.ipi_cst
        elif line.ipi_cst == "53":
            IPINT = etree.SubElement(ipi, "IPINT")
            CST = etree.SubElement(IPINT, "CST")
            CST.text = line.ipi_cst
        else:
            raise ValidationError(
                f"Geração de XML: (Produto: {line.product_description}) CST({line.ipi_cst}) do IPI não é suportado para o Simples Nacional."
            )

    elif issuer_fiscal_framework in ("3") and emission_finality in ("1", "2"):
        if not line.product_id.fiscal_type_id.code in ("04"):
            # se não for um produto fabricado, o grupo IPI não é informado
            return

        ipi = etree.SubElement(root, "IPI")

        cEnq = etree.SubElement(ipi, "cEnq")
        cEnq.text = line.ipi_guideline_code

        if line.is_ipi_with_percentage:
            IPITrib = etree.SubElement(ipi, "IPITrib")

            CST = etree.SubElement(IPITrib, "CST")
            CST.text = line.ipi_cst

            if line.is_ipi_with_percentage and line.ipi_tax_percent > 0:
                vBC = etree.SubElement(IPITrib, "vBC")
                vBC.text = f"{line.ipi_bc_value:.2f}"

                pIPI = etree.SubElement(IPITrib, "pIPI")
                pIPI.text = f"{line.ipi_tax_percent:.4f}"

            if line.is_ipi_qtt:
                if not line.ipi_unit_value or not line.ipi_unit_quantity:
                    raise ValidationError(
                        _(
                            f"Geração de XML: (Produto: {line.product_description})"
                            f"Grupo IPI Quantidade deve ser informado com todos os campos: Valor na Unidade Tributável e Quantidade na Unidade Tributável."
                        )
                    )

                qUnid = etree.SubElement(IPITrib, "qUnid")
                qUnid.text = f"{line.ipi_unit_quantity:.4f}"

                vUnid = etree.SubElement(IPITrib, "vUnid")
                vUnid.text = f"{line.ipi_unit_value:.4f}"

            vIPI = etree.SubElement(IPITrib, "vIPI")
            vIPI.text = f"{line.ipi_value:.2f}"
        else:
            IPINTrib = etree.SubElement(ipi, "IPINT")

            CST = etree.SubElement(IPINTrib, "CST")
            CST.text = line.ipi_cst


def buildPIS(root, line):
    issuer_fiscal_framework = line.nfe_id.issuer_fiscal_framework
    emission_finality = line.nfe_id.emission_finality

    if issuer_fiscal_framework in ("1", "2") and emission_finality in ("1", "2"):
        if (
            line.pis_cst != "99"
            or line.pis_bc_value != 0.00
            or line.pis_tax_percent != 0.00
            or line.pis_value != 0.00
        ):
            raise ValidationError(
                f"Geração de XML: (Produto: {line.product_description}) CST({line.pis_cst}) do PIS não é suportado para o Simples Nacional."
            )
        pis = etree.SubElement(root, "PIS")

        PISOutr = etree.SubElement(pis, "PISOutr")

        CST = etree.SubElement(PISOutr, "CST")
        CST.text = line.pis_cst

        vBC = etree.SubElement(PISOutr, "vBC")
        vBC.text = f"{line.pis_bc_value:.2f}"

        pPIS = etree.SubElement(PISOutr, "pPIS")
        pPIS.text = f"{line.pis_tax_percent:.4f}"

        vPIS = etree.SubElement(PISOutr, "vPIS")
        vPIS.text = f"{line.pis_value:.2f}"

    elif issuer_fiscal_framework in ("3") and emission_finality in ("1", "2"):
        pis = etree.SubElement(root, "PIS")
        pis_cst = line.pis_cst

        if pis_cst in ("01", "02"):
            PISAliq = etree.SubElement(pis, "PISAliq")
            CST = etree.SubElement(PISAliq, "CST")
            CST.text = line.pis_cst

            vBC = etree.SubElement(PISAliq, "vBC")
            vBC.text = f"{line.pis_bc_value:.2f}"

            pPIS = etree.SubElement(PISAliq, "pPIS")
            pPIS.text = f"{line.pis_tax_percent:.4f}"

            vPIS = etree.SubElement(PISAliq, "vPIS")
            vPIS.text = f"{line.pis_value:.2f}"

        elif pis_cst in ("03"):
            PISQtde = etree.SubElement(pis, "PISQtde")
            CST = etree.SubElement(PISQtde, "CST")
            CST.text = line.pis_cst

            qBCProd = etree.SubElement(PISQtde, "qBCProd")
            qBCProd.text = f"{line.pis_bc_quantity:.4f}"

            vAliqProd = etree.SubElement(PISQtde, "vAliqProd")
            vAliqProd.text = f"{line.pis_tax_quantity:.4f}"

            vPIS = etree.SubElement(PISQtde, "vPIS")
            vPIS.text = f"{line.pis_value:.2f}"

        elif pis_cst in ("04", "05", "06", "07", "08", "09"):
            PISNT = etree.SubElement(pis, "PISNT")
            CST = etree.SubElement(PISNT, "CST")
            CST.text = line.pis_cst

        elif pis_cst in (
            "49",  # Outras Operações de Saída
            "50",  # Operação com Direito a Crédito - Vinculada Exclusivamente a Receita Tributada no Mercado Interno
            "51",  # Operação com Direito a Crédito - Vinculada Exclusivamente a Receita Não Tributada no Mercado Interno
            "52",  # Operação com Direito a Crédito – Vinculada Exclusivamente a Receita de Exportação
            "53",  # Operação com Direito a Crédito - Vinculada a Receitas Tributadas e Não-Tributadas no Mercado Interno
            "54",  # Operação com Direito a Crédito - Vinculada a Receitas Tributadas no Mercado Interno e de Exportação
            "55",  # Operação com Direito a Crédito - Vinculada a Receitas Não-Tributadas no Mercado Interno e de Exportação
            "56",  # Operação com Direito a Crédito - Vinculada a Receitas Tributadas e Não-Tributadas no Mercado Interno, e de Exportação
            "60",  # Crédito Presumido - Operação de Aquisição Vinculada Exclusivamente a Receita Tributada no Mercado Interno
            "61",  # Crédito Presumido - Operação de Aquisição Vinculada Exclusivamente a Receita Não-Tributada no Mercado Interno
            "62",  # Crédito Presumido - Operação de Aquisição Vinculada Exclusivamente a Receita de Exportação
            "63",  # Crédito Presumido - Operação de Aquisição Vinculada a Receitas Tributadas e Não-Tributadas no Mercado Interno
            "64",  # Crédito Presumido - Operação de Aquisição Vinculada a Receitas Tributadas no Mercado Interno e de Exportação
            "65",  # Crédito Presumido - Operação de Aquisição Vinculada a Receitas Não-Tributadas no Mercado Interno e de Exportação
            "66",  # Crédito Presumido - Operação de Aquisição Vinculada a Receitas Tributadas e Não-Tributadas no Mercado Interno, e de Exportação
            "67",  # Crédito Presumido - Outras Operações
            "70",  # Operação de Aquisição sem Direito a Crédito
            "71",  # Operação de Aquisição com Isenção
            "72",  # Operação de Aquisição com Suspensão
            "73",  # Operação de Aquisição a Alíquota Zero
            "74",  # Operação de Aquisição sem Incidência da Contribuição
            "75",  # Operação de Aquisição por Substituição Tributária
            "98",  # Outras Operações de Entrada
            "99",  # Outras Operações
        ):
            PISOutr = etree.SubElement(pis, "PISOutr")
            CST = etree.SubElement(PISOutr, "CST")
            CST.text = line.pis_cst

            pis_perc_fields = [
                line.pis_bc_value,
                line.pis_tax_percent,
            ]

            is_pis_perc_required = any(pis_perc_fields) and not all(pis_perc_fields)
            if is_pis_perc_required:
                raise ValidationError(
                    f"Geração de XML: (Produto: {line.product_description}) Se o grupo do PIS Percentual for informado, é obrigatório informar todos os campos do grupo."
                )

            if is_pis_perc_required:
                vBC = etree.SubElement(PISOutr, "vBC")
                vBC.text = f"{line.pis_bc_value:.2f}"

                pPIS = etree.SubElement(PISOutr, "pPIS")
                pPIS.text = f"{line.pis_tax_percent:.4f}"

            pis_qtt_fields = [
                line.pis_bc_quantity,
                line.pis_tax_quantity,
            ]

            is_pis_qtt_required = any(pis_qtt_fields) and not all(pis_qtt_fields)
            if is_pis_qtt_required:
                raise ValidationError(
                    f"Geração de XML: (Produto: {line.product_description}) Se o grupo do PIS Quantidade for informado, é obrigatório informar todos os campos do grupo."
                )

            if is_pis_qtt_required:
                qBCProd = etree.SubElement(PISOutr, "qBCProd")
                qBCProd.text = f"{line.pis_bc_quantity:.4f}"

                vAliqProd = etree.SubElement(PISOutr, "vAliqProd")
                vAliqProd.text = f"{line.pis_tax_quantity:.4f}"

            vPIS = etree.SubElement(PISOutr, "vPIS")
            vPIS.text = f"{line.pis_value:.2f}"


def buildCOFINS(root, line):
    issuer_fiscal_framework = line.nfe_id.issuer_fiscal_framework
    emission_finality = line.nfe_id.emission_finality

    if issuer_fiscal_framework in ("1", "2") and emission_finality in ("1", "2"):
        if (
            line.cofins_cst != "99"
            or line.cofins_bc_value != 0.00
            or line.cofins_tax_percent != 0.00
            or line.cofins_value != 0.00
        ):
            raise ValidationError(
                f"Geração de XML: (Produto: {line.product_description}) CST({line.cofins_cst}) do COFINS não é suportado para o Simples Nacional."
            )
        cofins = etree.SubElement(root, "COFINS")

        COFINSOutr = etree.SubElement(cofins, "COFINSOutr")

        CST = etree.SubElement(COFINSOutr, "CST")
        CST.text = line.cofins_cst

        vBC = etree.SubElement(COFINSOutr, "vBC")
        vBC.text = f"{line.cofins_bc_value:.2f}"

        pCOFINS = etree.SubElement(COFINSOutr, "pCOFINS")
        pCOFINS.text = f"{line.cofins_tax_percent:.4f}"

        vCOFINS = etree.SubElement(COFINSOutr, "vCOFINS")
        vCOFINS.text = f"{line.cofins_value:.2f}"

    elif issuer_fiscal_framework in ("3") and emission_finality in ("1", "2"):
        cofins = etree.SubElement(root, "COFINS")
        cofins_cst = line.cofins_cst

        if cofins_cst in ("01", "02"):
            COFINSAliq = etree.SubElement(cofins, "COFINSAliq")
            CST = etree.SubElement(COFINSAliq, "CST")
            CST.text = line.cofins_cst

            vBC = etree.SubElement(COFINSAliq, "vBC")
            vBC.text = f"{line.cofins_bc_value:.2f}"

            pCOFINS = etree.SubElement(COFINSAliq, "pCOFINS")
            pCOFINS.text = f"{line.cofins_tax_percent:.4f}"

            vCOFINS = etree.SubElement(COFINSAliq, "vCOFINS")
            vCOFINS.text = f"{line.cofins_value:.2f}"

        elif cofins_cst in ("03"):
            COFINSQtde = etree.SubElement(cofins, "COFINSQtde")
            CST = etree.SubElement(COFINSQtde, "CST")
            CST.text = line.cofins_cst

            qBCProd = etree.SubElement(COFINSQtde, "qBCProd")
            qBCProd.text = f"{line.cofins_bc_quantity:.4f}"

            vAliqProd = etree.SubElement(COFINSQtde, "vAliqProd")
            vAliqProd.text = f"{line.cofins_tax_quantity:.4f}"

            vCOFINS = etree.SubElement(COFINSQtde, "vCOFINS")
            vCOFINS.text = f"{line.cofins_value:.2f}"

        elif cofins_cst in ("04", "05", "06", "07", "08", "09"):
            COFINSNT = etree.SubElement(cofins, "COFINSNT")
            CST = etree.SubElement(COFINSNT, "CST")
            CST.text = line.cofins_cst

        elif cofins_cst in (
            "49",  # Outras Operações de Saída
            "50",  # Operação com Direito a Crédito - Vinculada Exclusivamente a Receita Tributada no Mercado Interno
            "51",  # Operação com Direito a Crédito - Vinculada Exclusivamente a Receita Não Tributada no Mercado Interno
            "52",  # Operação com Direito a Crédito – Vinculada Exclusivamente a Receita de Exportação
            "53",  # Operação com Direito a Crédito - Vinculada a Receitas Tributadas e Não-Tributadas no Mercado Interno
            "54",  # Operação com Direito a Crédito - Vinculada a Receitas Tributadas no Mercado Interno e de Exportação
            "55",  # Operação com Direito a Crédito - Vinculada a Receitas Não-Tributadas no Mercado Interno e de Exportação
            "56",  # Operação com Direito a Crédito - Vinculada a Receitas Tributadas e Não-Tributadas no Mercado Interno, e de Exportação
            "60",  # Crédito Presumido - Operação de Aquisição Vinculada Exclusivamente a Receita Tributada no Mercado Interno
            "61",  # Crédito Presumido - Operação de Aquisição Vinculada Exclusivamente a Receita Não-Tributada no Mercado Interno
            "62",  # Crédito Presumido - Operação de Aquisição Vinculada Exclusivamente a Receita de Exportação
            "63",  # Crédito Presumido - Operação de Aquisição Vinculada a Receitas Tributadas e Não-Tributadas no Mercado Interno
            "64",  # Crédito Presumido - Operação de Aquisição Vinculada a Receitas Tributadas no Mercado Interno e de Exportação
            "65",  # Crédito Presumido - Operação de Aquisição Vinculada a Receitas Não-Tributadas no Mercado Interno e de Exportação
            "66",  # Crédito Presumido - Operação de Aquisição Vinculada a Receitas Tributadas e Não-Tributadas no Mercado Interno, e de Exportação
            "67",  # Crédito Presumido - Outras Operações
            "70",  # Operação de Aquisição sem Direito a Crédito
            "71",  # Operação de Aquisição com Isenção
            "72",  # Operação de Aquisição com Suspensão
            "73",  # Operação de Aquisição a Alíquota Zero
            "74",  # Operação de Aquisição sem Incidência da Contribuição
            "75",  # Operação de Aquisição por Substituição Tributária
            "98",  # Outras Operações de Entrada
            "99",  # Outras Operações
        ):
            COFINSOutr = etree.SubElement(cofins, "COFINSOutr")
            CST = etree.SubElement(COFINSOutr, "CST")
            CST.text = line.cofins_cst

            cofins_perc_fields = [
                line.cofins_bc_value,
                line.cofins_tax_percent,
            ]

            is_cofins_perc_required = any(cofins_perc_fields) and not all(
                cofins_perc_fields
            )
            if is_cofins_perc_required:
                raise ValidationError(
                    f"Geração de XML: (Produto: {line.product_description}) Se o grupo do COFINS Percentual for informado, é obrigatório informar todos os campos do grupo."
                )

            if is_cofins_perc_required:
                vBC = etree.SubElement(COFINSOutr, "vBC")
                vBC.text = f"{line.cofins_bc_value:.2f}"

                pCOFINS = etree.SubElement(COFINSOutr, "pCOFINS")
                pCOFINS.text = f"{line.cofins_tax_percent:.4f}"

            cofins_qtt_fields = [
                line.cofins_bc_quantity,
                line.cofins_tax_quantity,
            ]

            is_cofins_qtt_required = any(cofins_qtt_fields) and not all(
                cofins_qtt_fields
            )
            if is_cofins_qtt_required:
                raise ValidationError(
                    f"Geração de XML: (Produto: {line.product_description}) Se o grupo do COFINS Quantidade for informado, é obrigatório informar todos os campos do grupo."
                )

            if is_cofins_qtt_required:
                qBCProd = etree.SubElement(COFINSOutr, "qBCProd")
                qBCProd.text = f"{line.cofins_bc_quantity:.4f}"

                vAliqProd = etree.SubElement(COFINSOutr, "vAliqProd")
                vAliqProd.text = f"{line.cofins_tax_quantity:.4f}"

            vCOFINS = etree.SubElement(COFINSOutr, "vCOFINS")
            vCOFINS.text = f"{line.cofins_value:.2f}"


def buildICMS(imposto, nfe_document_line, is_final_customer):
    """
    Constrói o XML do ICMS conforme layout NFe 4.00

    Args:
        icms_root: Elemento <ICMS> onde serão adicionados os subelementos
        nfe_document_line: Linha do documento NFe com os dados tributários
    """
    # Determina se é Simples Nacional (CSOSN) ou Regime Normal (CST)
    icms_cst_code = nfe_document_line.icms_cst_code
    icms_origin = nfe_document_line.icms_origin

    # Simples Nacional - CSOSN (101, 102, 103, 201, 202, 203, 300, 400, 500, 900)
    if icms_cst_code in (
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
        _buildICMSSN(
            imposto, nfe_document_line, icms_origin, icms_cst_code, is_final_customer
        )
    elif icms_cst_code in (
        "00",
        "10",
        "20",
        "30",
        "40",
        "41",
        "50",
        "51",
        "60",
        "70",
        "90",
    ):
        _buildICMSRegimeNormal(imposto, nfe_document_line, icms_origin, icms_cst_code)
    else:
        raise ValidationError(
            f"Geração de XML: (Produto: {nfe_document_line.product_description}) CST({icms_cst_code}) do ICMS não é suportado."
        )


def _build_icms_deson(parent, line):
    """Appends vICMSDeson and motDesICMS sub-elements to *parent* when the
    ICMS desoneração group is present on *line*.

    Raises ValidationError when only one of the two required fields is set.
    """
    icms_deson_fields = [
        line.icms_deson_value,
        line.icms_deson_reason,
    ]

    if not any(icms_deson_fields):
        return

    if not all(icms_deson_fields):
        raise ValidationError(
            f"Geração de XML: (Produto: {line.product_description}) Se o grupo do ICMS Desoneração for informado, é obrigatório informar o Valor do ICMS Desoneração e o Motivo da Desoneração do ICMS."
        )

    vICMSDeson = etree.SubElement(parent, "vICMSDeson")
    vICMSDeson.text = f"{line.icms_deson_value:.2f}"

    motDesICMS = etree.SubElement(parent, "motDesICMS")
    motDesICMS.text = line.icms_deson_reason.code


def _buildICMSRegimeNormal(imposto, line, origin, cst):
    """Constrói XML ICMS para Regime Normal conforme Manual NFe 4.00"""
    # Grupo N - ICMS
    icms_root = etree.SubElement(imposto, "ICMS")

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
        modBC.text = line.icms_bc_modality

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
        if line.icms_fcp_tax_id:
            # N17c - Percentual FCP (opcional)
            pFCP = etree.SubElement(icms00, "pFCP")
            pFCP.text = f"{line.icms_fcp_tax_percent:.2f}"

            # N17d - Valor FCP (opcional)
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
        modBC.text = line.icms_bc_modality

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
        if line.icms_fcp_tax_id:
            vBCFCP = etree.SubElement(icms10, "vBCFCP")
            vBCFCP.text = f"{line.icms_fcp_bc_value:.2f}"

            pFCP = etree.SubElement(icms10, "pFCP")
            pFCP.text = f"{line.icms_fcp_tax_percent:.2f}"

            vFCP = etree.SubElement(icms10, "vFCP")
            vFCP.text = f"{line.icms_fcp_value:.2f}"

        # N18 - Modalidade BC ST (obrigatório)
        modBCST = etree.SubElement(icms10, "modBCST")
        modBCST.text = line.icms_st_modality

        if line.icms_st_modality == "4" and not line.icms_st_mva_percent:
            raise ValidationError(
                f"Geração de XML: (Produto: {line.product_description}) MVA ICMS ST é obrigatório para a modalidade da Base de Calculo do ICMS ST Margem Valor Agregado (%)."
            )
        # N19 - MVA ST
        if line.icms_st_mva_percent and line.icms_st_modality == "4":
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
        modBC.text = line.icms_bc_modality

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
        if line.icms_fcp_tax_id:
            vBCFCP = etree.SubElement(icms20, "vBCFCP")
            vBCFCP.text = f"{line.icms_fcp_bc_value:.2f}"

            pFCP = etree.SubElement(icms20, "pFCP")
            pFCP.text = f"{line.icms_fcp_tax_percent:.2f}"

            vFCP = etree.SubElement(icms20, "vFCP")
            vFCP.text = f"{line.icms_fcp_value:.2f}"

        # N17c-d - ICMS Desoneração (opcional)
        _build_icms_deson(icms20, line)

    elif cst == "30":
        # N05 - Isenta ou não tributada com cobrança de ICMS por ST
        icms30 = etree.SubElement(icms_root, "ICMS30")

        orig = etree.SubElement(icms30, "orig")
        orig.text = origin

        CST = etree.SubElement(icms30, "CST")
        CST.text = cst

        if line.icms_st_modality == "4" and not line.icms_st_mva_percent:
            raise ValidationError(
                f"Geração de XML: (Produto: {line.product_description}) MVA ICMS ST é obrigatório para a modalidade da Base de Calculo do ICMS ST Margem Valor Agregado (%)."
            )

        # N18 - Modalidade BC ST (obrigatório)
        modBCST = etree.SubElement(icms30, "modBCST")
        modBCST.text = line.icms_st_modality

        # N19 - MVA ST (opcional)
        if line.icms_st_mva_percent and line.icms_st_modality == "4":
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
        if line.icms_fcp_tax_id:
            vBCFCPST = etree.SubElement(icms30, "vBCFCPST")
            vBCFCPST.text = f"{line.icms_st_fcp_bc_value:.2f}"

            pFCPST = etree.SubElement(icms30, "pFCPST")
            pFCPST.text = f"{line.icms_st_fcp_tax_percent:.2f}"

            vFCPST = etree.SubElement(icms30, "vFCPST")
            vFCPST.text = f"{line.icms_st_fcp_value:.2f}"

        _build_icms_deson(icms30, line)

    elif cst in ("40", "41", "50"):
        # N06 - Isenta (40) / Não tributada (41) / Suspensão (50)
        icms40 = etree.SubElement(icms_root, "ICMS40")

        orig = etree.SubElement(icms40, "orig")
        orig.text = origin

        CST = etree.SubElement(icms40, "CST")
        CST.text = cst

        _build_icms_deson(icms40, line)

    elif cst == "51":
        # N07 - Diferimento
        icms51 = etree.SubElement(icms_root, "ICMS51")

        orig = etree.SubElement(icms51, "orig")
        orig.text = origin

        CST = etree.SubElement(icms51, "CST")
        CST.text = cst

        icms_deferment_fields = [
            line.icms_bc_modality,
            line.icms_bc_reduction_percent,
            line.icms_bc_value,
            line.icms_tax_percent,
            line.icms_value,
            line.icms_deferment_percent,
            line.icms_deferment_value,
            line.icms_deferment_payable,
        ]

        is_deferment_required = any(icms_deferment_fields) and not all(
            icms_deferment_fields
        )
        if is_deferment_required:
            raise ValidationError(
                f"Geração de XML: (Produto: {line.product_description}) Se o grupo do ICMS Diferimento for informado, é obrigatório informar todos os campos do grupo."
            )

        if is_deferment_required:
            # N13 - Modalidade BC
            modBC = etree.SubElement(icms51, "modBC")
            modBC.text = line.icms_bc_modality

            # N14 - Redução BC
            pRedBC = etree.SubElement(icms51, "pRedBC")
            pRedBC.text = f"{line.icms_bc_reduction_percent:.4f}"

            # N15 - Valor BC
            vBC = etree.SubElement(icms51, "vBC")
            vBC.text = f"{line.icms_bc_value:.2f}"

            # N16 - Alíquota
            pICMS = etree.SubElement(icms51, "pICMS")
            pICMS.text = f"{line.icms_tax_percent:.2f}"

            # N17 - Valor ICMS Operação - como se nao tivesse diferimento
            vICMSOp = etree.SubElement(icms51, "vICMSOp")
            vICMSOp.text = f"{line.icms_value:.2f}"

            # N26 - Percentual diferimento
            pDif = etree.SubElement(icms51, "pDif")
            pDif.text = f"{line.icms_deferment_percent:.4f}"

            # N27 - Valor ICMS diferido
            vICMSDif = etree.SubElement(icms51, "vICMSDif")
            vICMSDif.text = f"{line.icms_deferment_value:.2f}"

            # N17 - Valor ICMS
            vICMS = etree.SubElement(icms51, "vICMS")
            vICMS.text = f"{line.icms_deferment_payable:.2f}"

        # N17b-d - FCP (opcional)
        if line.icms_fcp_tax_id:
            vBCFCP = etree.SubElement(icms51, "vBCFCP")
            vBCFCP.text = f"{line.icms_fcp_bc_value:.2f}"

            pFCP = etree.SubElement(icms51, "pFCP")
            pFCP.text = f"{line.icms_fcp_tax_percent:.2f}"

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
        modBC.text = line.icms_bc_modality

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
        if line.icms_fcp_tax_id:
            vBCFCP = etree.SubElement(icms70, "vBCFCP")
            vBCFCP.text = f"{line.icms_fcp_bc_value:.2f}"

            pFCP = etree.SubElement(icms70, "pFCP")
            pFCP.text = f"{line.icms_fcp_tax_percent:.2f}"

            vFCP = etree.SubElement(icms70, "vFCP")
            vFCP.text = f"{line.icms_fcp_value:.2f}"

        # N18 - Modalidade BC ST (obrigatório)
        modBCST = etree.SubElement(icms70, "modBCST")
        modBCST.text = line.icms_st_modality

        if line.icms_st_modality == "4" and not line.icms_st_mva_percent:
            raise ValidationError(
                f"Geração de XML: (Produto: {line.product_description}) MVA ICMS ST é obrigatório para a modalidade da Base de Calculo do ICMS ST Margem Valor Agregado (%)."
            )

        # N19 - MVA ST (opcional)
        if line.icms_st_mva_percent and line.icms_st_modality == "4":
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
        if line.icms_fcp_tax_id:
            vBCFCPST = etree.SubElement(icms70, "vBCFCPST")
            vBCFCPST.text = f"{line.icms_st_fcp_bc_value:.2f}"

            pFCPST = etree.SubElement(icms70, "pFCPST")
            pFCPST.text = f"{line.icms_st_fcp_tax_percent:.2f}"

            vFCPST = etree.SubElement(icms70, "vFCPST")
            vFCPST.text = f"{line.icms_st_fcp_value:.2f}"

        _build_icms_deson(icms70, line)

    elif cst == "90":
        # N10 - Outros
        icms90 = etree.SubElement(icms_root, "ICMS90")

        orig = etree.SubElement(icms90, "orig")
        orig.text = origin

        CST = etree.SubElement(icms90, "CST")
        CST.text = cst

        icms_fields = [
            line.modBC,
            line.vBC,
            line.pRedBC,
            line.pICMS,
            line.vICMS,
        ]

        is_icms_required = any(icms_fields) and not all(icms_fields)
        if is_icms_required:
            raise ValidationError(
                f"Geração de XML: (Produto: {line.product_description}) Se o grupo do ICMS for informado, é obrigatório informar todos os campos do grupo."
            )

        if is_icms_required:
            modBC = etree.SubElement(icms90, "modBC")
            modBC.text = line.icms_bc_modality

            vBC = etree.SubElement(icms90, "vBC")
            vBC.text = f"{line.icms_bc_value:.2f}"

            pRedBC = etree.SubElement(icms90, "pRedBC")
            pRedBC.text = f"{line.icms_bc_reduction_percent:.4f}"

            pICMS = etree.SubElement(icms90, "pICMS")
            pICMS.text = f"{line.icms_tax_percent:.2f}"

            vICMS = etree.SubElement(icms90, "vICMS")
            vICMS.text = f"{line.icms_value:.2f}"

        # FCP (opcional)
        if line.icms_fcp_tax_id:
            vBCFCP = etree.SubElement(icms90, "vBCFCP")
            vBCFCP.text = f"{line.icms_fcp_bc_value:.2f}"

            pFCP = etree.SubElement(icms90, "pFCP")
            pFCP.text = f"{line.icms_fcp_tax_percent:.2f}"

            vFCP = etree.SubElement(icms90, "vFCP")
            vFCP.text = f"{line.icms_fcp_value:.2f}"

        icms_st_fields = [
            line.modBCST,
            line.pMVAST,
            line.pRedBCST,
            line.vBCST,
            line.pICMSST,
            line.vICMSST,
        ]

        is_icms_st_required = any(icms_st_fields) and not all(icms_st_fields)
        if is_icms_st_required:
            raise ValidationError(
                f"Geração de XML: (Produto: {line.product_description}) Se o grupo do ICMS ST for informado, é obrigatório informar todos os campos do grupo."
            )

        if is_icms_st_required:
            modBCST = etree.SubElement(icms90, "modBCST")
            modBCST.text = line.icms_st_modality

            if line.icms_st_modality == "4" and not line.icms_st_mva_percent:
                raise ValidationError(
                    f"Geração de XML: (Produto: {line.product_description}) MVA ICMS ST é obrigatório para a modalidade da Base de Calculo do ICMS ST Margem Valor Agregado (%)."
                )

            if line.icms_st_mva_percent and line.icms_st_modality == "4":
                pMVAST = etree.SubElement(icms90, "pMVAST")
                pMVAST.text = f"{line.icms_st_mva_percent:.4f}"

            if line.icms_st_reduction_percent:
                pRedBCST = etree.SubElement(icms90, "pRedBCST")
                pRedBCST.text = f"{line.icms_st_reduction_percent:.4f}"

            vBCST = etree.SubElement(icms90, "vBCST")
            vBCST.text = f"{line.icms_st_bc_value:.2f}"

            pICMSST = etree.SubElement(icms90, "pICMSST")
            pICMSST.text = f"{line.icms_st_tax_percent:.2f}"

            vICMSST = etree.SubElement(icms90, "vICMSST")
            vICMSST.text = f"{line.icms_st_value:.2f}"

        # FCP ST (opcional)
        if line.icms_fcp_tax_id:
            vBCFCPST = etree.SubElement(icms90, "vBCFCPST")
            vBCFCPST.text = f"{line.icms_st_fcp_bc_value:.2f}"

            pFCPST = etree.SubElement(icms90, "pFCPST")
            pFCPST.text = f"{line.icms_st_fcp_tax_percent:.2f}"

            vFCPST = etree.SubElement(icms90, "vFCPST")
            vFCPST.text = f"{line.icms_st_fcp_value:.2f}"

        _build_icms_deson(icms90, line)


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

        # N29 - Alíquota de crédito (obrigatório)
        pCredSN = etree.SubElement(icmssn201, "pCredSN")
        pCredSN.text = f"{line.icms_sn_credit_percent:.4f}"

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
            f"Geração de XML: (Produto: {line.product_description}) Modalidade da Base de Calculo do ICMS ST é obrigatório dentro do grupo do ICMS ST."
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
            f"Geração de XML: (Produto: {line.product_description}) Valor da Base de Calculo do ICMS ST é obrigatório dentro do grupo do ICMS ST."
        )
    vBCST = etree.SubElement(icmssn_root, "vBCST")
    vBCST.text = f"{line.icms_st_bc_value:.2f}"

    # N22 - Alíquota ICMS ST (obrigatório)
    if not line.icms_st_tax_percent or line.icms_st_tax_percent <= 0:
        raise ValidationError(
            f"Geração de XML: (Produto: {line.product_description}) Alíquota do ICMS ST é obrigatório dentro do grupo do ICMS ST."
        )
    pICMSST = etree.SubElement(icmssn_root, "pICMSST")
    pICMSST.text = f"{line.icms_st_tax_percent:.2f}"

    # N23 - Valor ICMS ST (obrigatório)
    if not line.icms_st_value or line.icms_st_value < 0:
        raise ValidationError(
            f"Geração de XML: (Produto: {line.product_description}) Valor do ICMS ST é obrigatório dentro do grupo do ICMS ST."
        )
    vICMSST = etree.SubElement(icmssn_root, "vICMSST")
    vICMSST.text = f"{line.icms_st_value:.2f}"

    if line.icms_st_fcp_tax_id:
        if not line.icms_st_fcp_bc_value or line.icms_st_fcp_bc_value <= 0:
            raise ValidationError(
                f"Geração de XML: (Produto: {line.product_description}) Valor da Base de Calculo do FCP ST é obrigatório quando o FCP ST está sendo informado."
            )

        vBCFCPST = etree.SubElement(icmssn_root, "vBCFCPST")
        vBCFCPST.text = f"{line.icms_st_fcp_bc_value:.2f}"

        if not line.icms_st_fcp_tax_percent or line.icms_st_fcp_tax_percent <= 0:
            raise ValidationError(
                f"Geração de XML: (Produto: {line.product_description}) Aliquota do FCP ST é obrigatório quando o FCP ST está sendo informado."
            )

        pFCPST = etree.SubElement(icmssn_root, "pFCPST")
        pFCPST.text = f"{line.icms_st_fcp_tax_percent:.2f}"

        if not line.icms_st_fcp_value or line.icms_st_fcp_value <= 0:
            raise ValidationError(
                f"Geração de XML: (Produto: {line.product_description}) Valor do FCP ST é obrigatório quando o FCP ST está sendo informado."
            )

        vFCPST = etree.SubElement(icmssn_root, "vFCPST")
        vFCPST.text = f"{line.icms_st_fcp_value:.2f}"


def printNfeXml(nfe_document):
    root = buildNfeXmlFromNfeDocumentModel(nfe_document)
    print(etree.tostring(root, pretty_print=True).decode("utf-8"))


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
    )

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
            if not record.recipient_id or not record.issuer_id:
                record.destination_id = False
            elif record.issuer_id.state_id == record.recipient_id.state_id:
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
    )

    @api.onchange("document_model")
    def _onchange_document_model_danfe(self):
        for record in self:
            # Reset danfe_print_format to valid default when document_model changes
            if record.document_model == "55":
                # For NF-e, valid options are 0, 1, 2, 3
                if record.danfe_print_format not in ["0", "1", "2", "3"]:
                    record.danfe_print_format = "1"
            elif record.document_model == "65":
                # For NFC-e, valid options are 0, 4, 5
                if record.danfe_print_format not in ["0", "4", "5"]:
                    record.danfe_print_format = "4"

    @api.constrains("danfe_print_format", "document_model")
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
        NFE_EMISSION_FINALITY,
        string="Finalidade da Emissão",
        required=True,
        default="1",
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

    @api.onchange("document_model")
    def _onchange_document_model_presence_indicator(self):
        for record in self:
            # Reset presence_indicator to valid default when document_model changes
            # For NFC-e (65), only options 1 (presencial) and 4 (entrega a domicílio) are valid
            if record.document_model == "65":
                if record.presence_indicator not in ["1", "4"]:
                    record.presence_indicator = False
            # nfe com presence_indicator == "4" (nfc-e com entrega a domicílio) nao é valido
            if record.document_model == "55" and record.presence_indicator == "4":
                record.presence_indicator = False

    @api.constrains("presence_indicator", "document_model")
    def _check_presence_indicator_document_model(self):
        for record in self:
            # For NFC-e (65), only options 1 (presencial) and 4 (entrega a domicílio) are valid
            if record.document_model == "65" and record.presence_indicator not in [
                "1",
                "4",
            ]:
                raise ValidationError(
                    _(
                        "Para NFC-e (modelo 65), o Indicador de Presença do Comprador "
                        "deve ser '1 - Operação presencial' ou '4 - NFC-e em operação com entrega a domicílio'."
                    )
                )
            if record.document_model == "55" and record.presence_indicator == "4":
                raise ValidationError(
                    _(
                        "NF-e com Indicador de Presença do Comprador '4' (NFC-e com entrega a domicílio) não é válido."
                    )
                )

    # Indicador de intermediador/marketplace. Criado na NT 2020.006.
    # (comentario adicionado por AI, verificar se é correto) Obrigatório se 'indIntermed' = 1, preencher 'infIntermed' (Grupo YB).
    intermediator_indicator = fields.Selection(
        INTERMEDIATOR_INDICATOR,
        string="Indicador de Intermediador/Marketplace",
    )

    @api.constrains("intermediator_indicator", "presence_indicator")
    def _check_intermediator_indicator(self):
        for record in self:
            if record.presence_indicator in [
                "2",
                "3",
                "4",
                "9",
            ]:
                if not record.intermediator_indicator:
                    raise ValidationError(
                        _(
                            "O Indicador de Intermediador/Marketplace é obrigatório para operações não presenciais."
                        )
                    )
            elif record.intermediator_indicator:
                raise ValidationError(
                    _(
                        "O Indicador de Intermediador/Marketplace só deve ser informado se"
                        " o Indicador de Presença do Comprador for 'Operação não presencial, pela Internet',"
                        " 'Operação não presencial, Teleatendimento', 'NFC-e em operação com entrega a domicílio'"
                        " ou 'Operação não presencial, outros'"
                    )
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

    @api.constrains("ref_nfe_numbers", "document_model")
    def _check_ref_nfe_numbers(self):
        for record in self:
            if record.document_model == "65" and len(record.ref_nfe_numbers) > 0:
                raise ValidationError(_("NFC-e não pode referenciar documento fiscal."))

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

    @api.constrains("issuer_cnpj", "issuer_id", "issuer_id.company_type")
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

    @api.constrains("issuer_cpf", "issuer_id", "issuer_id.company_type")
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

    @api.constrains("issuer_legal_name")
    def _check_issuer_legal_name(self):
        for record in self:
            if not record.issuer_legal_name:
                raise ValidationError(_("A Razão Social do Emitente é obrigatória."))

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

    @api.constrains("issuer_street")
    def _check_issuer_street(self):
        for record in self:
            if not record.issuer_street:
                raise ValidationError(_("O Logradouro do Emitente é obrigatório."))

    # Número do endereço do emitente.
    issuer_street_number = fields.Char(
        related="issuer_id.street_number",
        string="Número",
        store=True,
        size=60,
    )

    @api.constrains("issuer_street_number")
    def _check_issuer_street_number(self):
        for record in self:
            if not record.issuer_street_number:
                raise ValidationError(
                    _("O Número do Endereço do Emitente é obrigatório.")
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

    @api.constrains("issuer_district")
    def _check_issuer_district(self):
        for record in self:
            if not record.issuer_district:
                raise ValidationError(_("O Bairro do Emitente é obrigatório."))

    # Código do município do emitente. Usar Tabela IBGE.
    issuer_city_code = fields.Char(
        related="issuer_id.city_id.ibge_code",
        string="Código do Município",
        store=True,
        size=7,
    )

    @api.constrains("issuer_city_code")
    def _check_issuer_city_code(self):
        for record in self:
            if not record.issuer_city_code:
                raise ValidationError(
                    _("O Código do Município do Emitente é obrigatório.")
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

    @api.constrains("issuer_state")
    def _check_issuer_state(self):
        for record in self:
            if not record.issuer_state:
                raise ValidationError(_("A Sigla da UF do Emitente é obrigatória."))

    # Código do CEP do emitente. Informar zeros não significativos.
    issuer_zip = fields.Char(
        compute="_compute_issuer_zip",
        string="CEP",
        readonly=True,
        store=True,
        size=8,
    )

    @api.depends("issuer_id", "issuer_id.unformatted_zip")
    def _compute_issuer_zip(self):
        for record in self:
            if record.issuer_id and record.issuer_id.unformatted_zip:
                record.issuer_zip = record.issuer_id.unformatted_zip.zfill(8)
            else:
                record.issuer_zip = False

    @api.constrains("issuer_zip")
    def _check_issuer_zip(self):
        for record in self:
            if not record.issuer_zip:
                raise ValidationError(_("O CEP do Emitente é obrigatório."))

    # Código do País do emitente. 1058=Brasil. Opcional.
    issuer_country_code = fields.Integer(
        related="issuer_id.country_id.bacen_code",
        string="Código País",
        store=True,
        readonly=True,
    )

    @api.constrains("issuer_country_code")
    def _check_issuer_country_code(self):
        for record in self:
            if not record.issuer_country_code:
                raise ValidationError(_("O Código do País do Emitente é obrigatório."))

    # Nome do País do emitente. Brasil ou BRASIL. Opcional.
    issuer_country_name = fields.Char(
        string="Nome País",
        store=True,
        size=60,
        compute="_compute_issuer_country_name",
        readonly=True,
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
    # Não implementado. Informado na emissão de NF-e conjugada, com itens de produtos sujeitos ao ICMS e itens de serviços sujeitos ao ISSQN.
    issuer_im = fields.Char(
        # related="issuer_id.inscr_mun",
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
    )

    recipient_fiscal_framework = fields.Selection(
        related="recipient_id.fiscal_framework",
        string="Regime Fiscal do Destinatário",
        store=True,
        readonly=True,
    )

    @api.constrains("recipient_id", "document_model")
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
                record.recipient_id
                and record.recipient_id.company_type == "company"
                and record.recipient_id.vat
                and len(record.recipient_id.vat) == 14
                # para uso futuro. No momento, o recipient_id está sendo filtrado pelo domain [('country_id.code', '=', 'BR')]
                and not record.recipient_id.is_foreign
            ):
                record.recipient_cnpj = record.recipient_id.vat
            else:
                record.recipient_cnpj = False

    @api.constrains(
        "recipient_cnpj",
        "recipient_id",
        "recipient_id.company_type",
        "recipient_id.is_foreign",
    )
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
                record.recipient_id
                and record.recipient_id.company_type == "person"
                and record.recipient_id.vat
                and len(record.recipient_id.vat) == 11
                and not record.recipient_id.is_foreign
            ):
                record.recipient_cpf = record.recipient_id.vat
            else:
                record.recipient_cpf = False

    @api.constrains(
        "recipient_cpf",
        "recipient_id",
        "recipient_id.company_type",
        "recipient_id.is_foreign",
    )
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
            if record.recipient_id and record.recipient_id.is_foreign:
                record.recipient_foreign_id = record.recipient_id.vat
            else:
                record.recipient_foreign_id = False

    @api.constrains("recipient_foreign_id", "recipient_id", "recipient_id.is_foreign")
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

    @api.constrains("recipient_legal_name", "recipient_id")
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

    @api.constrains("recipient_street", "recipient_id")
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

    @api.constrains("recipient_street_number", "recipient_id")
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

    @api.constrains("recipient_district", "recipient_id")
    def _check_recipient_district(self):
        for record in self:
            if record.recipient_id and not record.recipient_district:
                raise ValidationError(_("O Bairro do Destinatário é obrigatório."))

    # Código do município do destinatário. Usar Tabela IBGE.
    recipient_city_code = fields.Char(
        compute="_compute_recipient_city_code",
        string="Código Município Destinatário",
        readonly=True,
        store=True,
        size=7,
    )

    @api.depends(
        "recipient_id",
        "recipient_id.city_id",
        "recipient_id.is_foreign",
    )
    def _compute_recipient_city_code(self):
        for record in self:
            if record.recipient_id and record.recipient_id.is_foreign:
                record.recipient_city_code = "9999999"
            elif record.recipient_id and record.recipient_id.city_id:
                record.recipient_city_code = record.recipient_id.city_id.ibge_code
            else:
                record.recipient_city_code = False

    @api.constrains("recipient_city_code", "recipient_id")
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
            if record.recipient_id:
                if record.recipient_id.is_foreign:
                    record.recipient_city_name = "EXTERIOR"
                elif record.recipient_id.city_id:
                    record.recipient_city_name = (
                        record.recipient_id.city_id.with_context(lang="pt_BR").name
                    )
                else:
                    record.recipient_city_name = False

    @api.constrains("recipient_city_name", "recipient_id")
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

    @api.constrains("recipient_state", "recipient_id")
    def _check_recipient_state(self):
        for record in self:
            if record.recipient_id and not record.recipient_state:
                raise ValidationError(_("A Sigla da UF do Destinatário é obrigatória."))

    # Código do CEP do destinatário. Informar zeros não significativos. Opcional.
    recipient_zip = fields.Char(
        string="CEP Destinatário",
        store=True,
        size=8,
        compute="_compute_recipient_zip",
        readonly=True,
    )

    @api.depends("recipient_id", "recipient_id.unformatted_zip")
    def _compute_recipient_zip(self):
        for record in self:
            if record.recipient_id:
                if record.recipient_id.unformatted_zip:
                    # preencher com zeros não significativos
                    record.recipient_zip = record.recipient_id.unformatted_zip.zfill(8)
                else:
                    record.recipient_zip = False

    @api.constrains("recipient_zip", "recipient_id", "recipient_id.is_foreign")
    def _check_recipient_zip(self):
        for record in self:
            if record.recipient_id and not record.recipient_id.is_foreign:
                if not record.recipient_zip:
                    raise ValidationError(_("O CEP do Destinatário é obrigatório."))
                elif not (len(record.recipient_zip) == 8):
                    raise ValidationError(
                        _("O CEP do Destinatário deve ter 8 caracteres.")
                    )

    # Código do País do destinatário. Usar Tabela BACEN. Opcional.
    recipient_country_code = fields.Integer(
        related="recipient_id.country_id.bacen_code",
        string="Código País Destinatário",
        store=True,
        readonly=True,
    )

    @api.constrains("recipient_country_code", "recipient_id", "recipient_id.is_foreign")
    def _check_recipient_country_code(self):
        for record in self:
            if record.recipient_id and record.recipient_id.is_foreign:
                raise ValidationError(
                    _(
                        "O Código do País do Destinatário é obrigatório para operações com exterior."
                    )
                )

    # Nome do País do destinatário. Opcional.
    recipient_country_name = fields.Char(
        string="Nome País Destinatário",
        store=True,
        size=60,
        compute="_compute_recipient_country_name",
        readonly=True,
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

    @api.constrains("recipient_country_name", "recipient_id", "recipient_id.is_foreign")
    def _check_recipient_country_name(self):
        for record in self:
            if (
                record.recipient_id
                and record.recipient_id.is_foreign
                and not record.recipient_country_name
            ):
                raise ValidationError(
                    _(
                        "O Nome do País do Destinatário é obrigatório para operações com exterior."
                    )
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

    @api.depends("recipient_formatted_phone", "recipient_id")
    def _compute_recipient_phone(self):
        for record in self:
            if record.recipient_id and record.recipient_formatted_phone:
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

    # TODO revisar
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

    @api.constrains("recipient_ie_indicator", "recipient_id")
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
        readonly=True,
    )

    @api.depends("recipient_ie_indicator", "recipient_id", "recipient_id.inscr_est")
    def _compute_recipient_ie(self):
        for record in self:
            if record.recipient_ie_indicator == "1" and record.recipient_id.inscr_est:
                record.recipient_ie = record.recipient_id.inscr_est
            else:
                record.recipient_ie = False

    @api.constrains("recipient_ie", "recipient_id", "recipient_ie_indicator")
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

    # Grupo F - local de retirada (quando o local de retirada é diferente do endereço do emitente)

    is_retrieval_location_different_from_issuer_address = fields.Boolean(
        string="Local de Retirada Diferente do Endereço do Emitente",
        default=False,
    )

    retrieval_partner_id = fields.Many2one(
        comodel_name="res.partner",
        string="Local de Retirada",
        domain="[('country_id.code', '=', 'BR')]",
    )

    @api.constrains(
        "retrieval_partner_id",
        "is_retrieval_location_different_from_issuer_address",
    )
    def _check_retrieval_partner_id(self):
        for record in self:
            if (
                record.is_retrieval_location_different_from_issuer_address
                and not record.retrieval_partner_id
            ):
                raise ValidationError(
                    _(
                        "O Local de Retirada é obrigatório quando o local de retirada é diferente do endereço do emitente."
                    )
                )

    retrieval_cnpj = fields.Char(
        compute="_compute_retrieval_cnpj",
        string="CNPJ do Local de Retirada",
        store=True,
        size=14,
        readonly=True,
    )

    @api.depends(
        "is_retrieval_location_different_from_issuer_address",
        "retrieval_partner_id",
        "retrieval_partner_id.company_type",
        "retrieval_partner_id.vat",
    )
    def _compute_retrieval_cnpj(self):
        for record in self:
            if (
                record.is_retrieval_location_different_from_issuer_address
                and record.retrieval_partner_id
                and record.retrieval_partner_id.company_type == "company"
                and record.retrieval_partner_id.vat
                and len(record.retrieval_partner_id.vat) == 14
            ):
                record.retrieval_cnpj = record.retrieval_partner_id.vat
            else:
                record.retrieval_cnpj = False

    @api.constrains(
        "retrieval_cnpj",
        "is_retrieval_location_different_from_issuer_address",
        "retrieval_partner_id",
        "retrieval_partner_id.company_type",
    )
    def _check_retrieval_cnpj(self):
        for record in self:
            if (
                record.is_retrieval_location_different_from_issuer_address
                and record.retrieval_partner_id
                and record.retrieval_partner_id.company_type == "company"
            ):
                if not record.retrieval_cnpj:
                    raise ValidationError(
                        _("O CNPJ do Local de Retirada é obrigatório.")
                    )
                elif not (len(record.retrieval_cnpj) == 14):
                    raise ValidationError(
                        _("O CNPJ do Local de Retirada deve ter 14 caracteres.")
                    )

    retrieval_cpf = fields.Char(
        compute="_compute_retrieval_cpf",
        string="CPF do Local de Retirada",
        store=True,
        size=11,
        readonly=True,
    )

    @api.depends(
        "is_retrieval_location_different_from_issuer_address",
        "retrieval_partner_id",
        "retrieval_partner_id.company_type",
        "retrieval_partner_id.vat",
    )
    def _compute_retrieval_cpf(self):
        for record in self:
            if (
                record.is_retrieval_location_different_from_issuer_address
                and record.retrieval_partner_id
                and record.retrieval_partner_id.company_type == "person"
                and record.retrieval_partner_id.vat
                and len(record.retrieval_partner_id.vat) == 11
            ):
                record.retrieval_cpf = record.retrieval_partner_id.vat
            else:
                record.retrieval_cpf = False

    @api.constrains(
        "retrieval_cpf",
        "is_retrieval_location_different_from_issuer_address",
        "retrieval_partner_id",
        "retrieval_partner_id.company_type",
    )
    def _check_retrieval_cpf(self):
        for record in self:
            if (
                record.is_retrieval_location_different_from_issuer_address
                and record.retrieval_partner_id
                and record.retrieval_partner_id.company_type == "person"
            ):
                if not record.retrieval_cpf:
                    raise ValidationError(
                        _("O CPF do Local de Retirada é obrigatório.")
                    )
                elif not (len(record.retrieval_cpf) == 11):
                    raise ValidationError(
                        _("O CPF do Local de Retirada deve ter 11 caracteres.")
                    )

    retrieval_legal_name = fields.Char(
        related="retrieval_partner_id.legal_name",
        string="Razão Social/Nome do Local de Retirada",
        store=True,
        size=60,
    )

    retrieval_street = fields.Char(
        related="retrieval_partner_id.street",
        string="Logradouro do Local de Retirada",
        store=True,
        size=60,
    )

    @api.constrains(
        "retrieval_street",
        "is_retrieval_location_different_from_issuer_address",
        "retrieval_partner_id",
    )
    def _check_retrieval_street(self):
        for record in self:
            if (
                record.is_retrieval_location_different_from_issuer_address
                and record.retrieval_partner_id
                and not record.retrieval_street
            ):
                raise ValidationError(
                    _("O Logradouro do Local de Retirada é obrigatório.")
                )

    retrieval_street_number = fields.Char(
        related="retrieval_partner_id.street_number",
        string="Número do Local de Retirada",
        store=True,
        size=60,
    )

    @api.constrains(
        "retrieval_street_number",
        "is_retrieval_location_different_from_issuer_address",
        "retrieval_partner_id",
    )
    def _check_retrieval_street_number(self):
        for record in self:
            if (
                record.is_retrieval_location_different_from_issuer_address
                and record.retrieval_partner_id
                and not record.retrieval_street_number
            ):
                raise ValidationError(_("O Número do Local de Retirada é obrigatório."))

    retrieval_street_complement = fields.Char(
        related="retrieval_partner_id.street_complement",
        string="Complemento do Local de Retirada",
        store=True,
        size=60,
    )

    retrieval_district = fields.Char(
        related="retrieval_partner_id.district",
        string="Bairro do Local de Retirada",
        store=True,
        size=60,
    )

    @api.constrains(
        "retrieval_district",
        "is_retrieval_location_different_from_issuer_address",
        "retrieval_partner_id",
    )
    def _check_retrieval_district(self):
        for record in self:
            if (
                record.is_retrieval_location_different_from_issuer_address
                and record.retrieval_partner_id
                and not record.retrieval_district
            ):
                raise ValidationError(_("O Bairro do Local de Retirada é obrigatório."))

    retrieval_city_code = fields.Char(
        related="retrieval_partner_id.city_id.ibge_code",
        string="Código do Município do Local de Retirada",
        store=True,
        size=7,
    )

    @api.constrains(
        "retrieval_city_code",
        "is_retrieval_location_different_from_issuer_address",
        "retrieval_partner_id",
    )
    def _check_retrieval_city_code(self):
        for record in self:
            if (
                record.is_retrieval_location_different_from_issuer_address
                and record.retrieval_partner_id
                and not record.retrieval_city_code
            ):
                raise ValidationError(
                    _("O Código do Município do Local de Retirada é obrigatório.")
                )

    retrieval_city_name = fields.Char(
        compute="_compute_retrieval_city_name",
        string="Nome do Município do Local de Retirada",
        store=True,
        size=60,
    )

    @api.depends(
        "retrieval_partner_id",
        "retrieval_partner_id.city_id",
        "is_retrieval_location_different_from_issuer_address",
    )
    def _compute_retrieval_city_name(self):
        for record in self:
            if (
                record.is_retrieval_location_different_from_issuer_address
                and record.retrieval_partner_id
                and record.retrieval_partner_id.city_id
            ):
                record.retrieval_city_name = (
                    record.retrieval_partner_id.city_id.with_context(lang="pt_BR").name
                )
            else:
                record.retrieval_city_name = False

    @api.constrains(
        "retrieval_city_name",
        "is_retrieval_location_different_from_issuer_address",
        "retrieval_partner_id",
    )
    def _check_retrieval_city_name(self):
        for record in self:
            if (
                record.is_retrieval_location_different_from_issuer_address
                and record.retrieval_partner_id
                and not record.retrieval_city_name
            ):
                raise ValidationError(
                    _("O Nome do Município do Local de Retirada é obrigatório.")
                )

    retrieval_state = fields.Char(
        related="retrieval_partner_id.state_id.code",
        string="UF do Local de Retirada",
        store=True,
        size=2,
    )

    @api.constrains(
        "retrieval_state",
        "is_retrieval_location_different_from_issuer_address",
        "retrieval_partner_id",
    )
    def _check_retrieval_state(self):
        for record in self:
            if (
                record.is_retrieval_location_different_from_issuer_address
                and record.retrieval_partner_id
                and not record.retrieval_state
            ):
                raise ValidationError(_("A UF do Local de Retirada é obrigatória."))

    retrieval_zip = fields.Char(
        related="retrieval_partner_id.unformatted_zip",
        string="CEP do Local de Retirada",
        store=True,
        size=8,
    )

    @api.depends("retrieval_partner_id", "retrieval_partner_id.unformatted_zip")
    def _compute_retrieval_zip(self):
        for record in self:
            if (
                record.retrieval_partner_id
                and record.retrieval_partner_id.unformatted_zip
            ):
                record.retrieval_zip = (
                    record.retrieval_partner_id.unformatted_zip.zfill(8)
                )
            else:
                record.retrieval_zip = False

    retrieval_country_code = fields.Integer(
        related="retrieval_partner_id.country_id.bacen_code",
        string="Código do País do Local de Retirada",
        store=True,
        readonly=True,
    )

    retrieval_country_name = fields.Char(
        string="Nome do País do Local de Retirada",
        store=True,
        size=60,
        compute="_compute_retrieval_country_name",
        readonly=True,
    )

    @api.depends("retrieval_partner_id", "retrieval_partner_id.country_id")
    def _compute_retrieval_country_name(self):
        for record in self:
            if record.retrieval_partner_id.country_id:
                record.retrieval_country_name = (
                    record.retrieval_partner_id.country_id.with_context(
                        lang="pt_BR"
                    ).name
                )
            else:
                record.retrieval_country_name = False

    retrieval_formatted_phone = fields.Char(
        related="retrieval_partner_id.phone",
        string="Telefone do Local de Retirada",
        store=True,
    )

    retrieval_phone = fields.Char(
        compute="_compute_retrieval_phone",
        string="Telefone do Local de Retirada",
        store=True,
    )

    @api.depends("retrieval_formatted_phone")
    def _compute_retrieval_phone(self):
        for record in self:
            if record.retrieval_formatted_phone:
                record.retrieval_phone = "".join(
                    filter(str.isdigit, record.retrieval_formatted_phone)
                )
            else:
                record.retrieval_phone = False

    retrieval_email = fields.Char(
        related="retrieval_partner_id.nfe_document_email",
        string="Email do Local de Retirada",
        store=True,
        size=60,
    )

    retrieval_ie = fields.Char(
        related="retrieval_partner_id.inscr_est",
        string="Inscrição Estadual do Local de Retirada",
        store=True,
        size=14,
        readonly=True,
    )

    # === Grupo G Identificação do Local de Entrega ===

    is_delivery_location_different_from_recipient_address = fields.Boolean(
        string="Local de Entrega Diferente do Endereço do Destinatário",
        default=False,
    )

    # entrega - Local de Entrega. Ocorrência múltipla (máximo = 1).
    delivery_partner_id = fields.Many2one(
        comodel_name="res.partner",
        string="Local de Entrega",
        domain="[('country_id.code', '=', 'BR')]",
    )

    @api.constrains(
        "delivery_partner_id",
        "is_delivery_location_different_from_recipient_address",
    )
    def _check_delivery_partner_id(self):
        for record in self:
            if (
                record.is_delivery_location_different_from_recipient_address
                and not record.delivery_partner_id
            ):
                raise ValidationError(
                    _(
                        "O Local de Entrega é obrigatório quando o local de entrega é diferente do endereço do destinatário."
                    )
                )

    delivery_cnpj = fields.Char(
        compute="_compute_delivery_cnpj",
        string="CNPJ do Local de Entrega",
        store=True,
        size=14,
    )

    @api.depends(
        "is_delivery_location_different_from_recipient_address",
        "delivery_partner_id",
        "delivery_partner_id.vat",
        "delivery_partner_id.company_type",
        "delivery_partner_id.is_foreign",
    )
    def _compute_delivery_cnpj(self):
        for record in self:
            if (
                record.is_delivery_location_different_from_recipient_address
                and record.delivery_partner_id
                and record.delivery_partner_id.company_type == "company"
                and record.delivery_partner_id.vat
                and len(record.delivery_partner_id.vat) == 14
                and not record.delivery_partner_id.is_foreign
            ):
                record.delivery_cnpj = record.delivery_partner_id.vat
            else:
                record.delivery_cnpj = False

    @api.constrains(
        "delivery_cnpj",
        "is_delivery_location_different_from_recipient_address",
        "delivery_partner_id",
        "delivery_partner_id.company_type",
        "delivery_partner_id.is_foreign",
    )
    def _check_delivery_cnpj(self):
        for record in self:
            if (
                record.is_delivery_location_different_from_recipient_address
                and record.delivery_partner_id
                and record.delivery_partner_id.company_type == "company"
                and not record.delivery_partner_id.is_foreign
            ):
                if not record.delivery_cnpj:
                    raise ValidationError(
                        _("O CNPJ do Local de Entrega é obrigatório.")
                    )
                elif not (len(record.delivery_cnpj) == 14):
                    raise ValidationError(
                        _("O CNPJ do Local de Entrega deve ter 14 caracteres.")
                    )

    delivery_cpf = fields.Char(
        compute="_compute_delivery_cpf",
        string="CPF do Local de Entrega",
        store=True,
        size=11,
    )

    @api.depends(
        "is_delivery_location_different_from_recipient_address",
        "delivery_partner_id",
        "delivery_partner_id.company_type",
        "delivery_partner_id.vat",
        "delivery_partner_id.is_foreign",
    )
    def _compute_delivery_cpf(self):
        for record in self:
            if (
                record.is_delivery_location_different_from_recipient_address
                and record.delivery_partner_id
                and record.delivery_partner_id.company_type == "person"
                and record.delivery_partner_id.vat
                and len(record.delivery_partner_id.vat) == 11
                and not record.delivery_partner_id.is_foreign
            ):
                record.delivery_cpf = record.delivery_partner_id.vat
            else:
                record.delivery_cpf = False

    @api.constrains(
        "delivery_cpf",
        "is_delivery_location_different_from_recipient_address",
        "delivery_partner_id",
        "delivery_partner_id.company_type",
        "delivery_partner_id.is_foreign",
    )
    def _check_delivery_cpf(self):
        for record in self:
            if (
                record.is_delivery_location_different_from_recipient_address
                and record.delivery_partner_id
                and record.delivery_partner_id.company_type == "person"
                and not record.delivery_partner_id.is_foreign
            ):
                if not record.delivery_cpf:
                    raise ValidationError(_("O CPF do Local de Entrega é obrigatório."))
                elif not (len(record.delivery_cpf) == 11):
                    raise ValidationError(
                        _("O CPF do Local de Entrega deve ter 11 caracteres.")
                    )

    delivery_legal_name = fields.Char(
        related="delivery_partner_id.legal_name",
        string="Razão Social/Nome do Local de Entrega",
        store=True,
        size=60,
    )

    delivery_street = fields.Char(
        related="delivery_partner_id.street",
        string="Logradouro do Local de Entrega",
        store=True,
        size=60,
    )

    @api.constrains(
        "delivery_street",
        "is_delivery_location_different_from_recipient_address",
        "delivery_partner_id",
    )
    def _check_delivery_street(self):
        for record in self:
            if (
                record.is_delivery_location_different_from_recipient_address
                and record.delivery_partner_id
                and not record.delivery_street
            ):
                raise ValidationError(
                    _("O Logradouro do Local de Entrega é obrigatório.")
                )

    delivery_street_number = fields.Char(
        related="delivery_partner_id.street_number",
        string="Número do Logradouro do Local de Entrega",
        store=True,
        size=10,
    )

    @api.constrains(
        "delivery_street_number",
        "is_delivery_location_different_from_recipient_address",
        "delivery_partner_id",
    )
    def _check_delivery_street_number(self):
        for record in self:
            if (
                record.is_delivery_location_different_from_recipient_address
                and record.delivery_partner_id
                and not record.delivery_street_number
            ):
                raise ValidationError(
                    _("O Número do Logradouro do Local de Entrega é obrigatório.")
                )

    delivery_street_complement = fields.Char(
        related="delivery_partner_id.street_complement",
        string="Complemento do Logradouro do Local de Entrega",
        store=True,
        size=60,
    )

    delivery_district = fields.Char(
        related="delivery_partner_id.district",
        string="Bairro do Local de Entrega",
        store=True,
        size=60,
    )

    @api.constrains(
        "delivery_district",
        "is_delivery_location_different_from_recipient_address",
        "delivery_partner_id",
    )
    def _check_delivery_district(self):
        for record in self:
            if (
                record.is_delivery_location_different_from_recipient_address
                and record.delivery_partner_id
                and not record.delivery_district
            ):
                raise ValidationError(_("O Bairro do Local de Entrega é obrigatório."))

    delivery_city_code = fields.Char(
        compute="_compute_delivery_city_code",
        string="Código do Município do Local de Entrega",
        store=True,
        readonly=True,
        size=7,
    )

    @api.depends(
        "delivery_partner_id",
        "delivery_partner_id.city_id",
        "delivery_partner_id.is_foreign",
    )
    def _compute_delivery_city_code(self):
        for record in self:
            if record.delivery_partner_id and record.delivery_partner_id.is_foreign:
                record.delivery_city_code = "9999999"
            elif record.delivery_partner_id and record.delivery_partner_id.city_id:
                record.delivery_city_code = record.delivery_partner_id.city_id.ibge_code
            else:
                record.delivery_city_code = False

    @api.constrains(
        "delivery_city_code",
        "is_delivery_location_different_from_recipient_address",
        "delivery_partner_id",
    )
    def _check_delivery_city_code(self):
        for record in self:
            if (
                record.is_delivery_location_different_from_recipient_address
                and record.delivery_partner_id
                and not record.delivery_city_code
            ):
                raise ValidationError(
                    _("O Código do Município do Local de Entrega é obrigatório.")
                )

    delivery_city_name = fields.Char(
        compute="_compute_delivery_city_name",
        string="Nome do Município do Local de Entrega",
        store=True,
        size=60,
    )

    @api.depends(
        "delivery_partner_id",
        "delivery_partner_id.city_id",
        "delivery_partner_id.is_foreign",
    )
    def _compute_delivery_city_name(self):
        for record in self:
            if record.delivery_partner_id and record.delivery_partner_id.is_foreign:
                record.delivery_city_name = "EXTERIOR"
            elif record.delivery_partner_id and record.delivery_partner_id.city_id:
                record.delivery_city_name = (
                    record.delivery_partner_id.city_id.with_context(lang="pt_BR").name
                )
            else:
                record.delivery_city_name = False

    @api.constrains(
        "delivery_city_name",
        "is_delivery_location_different_from_recipient_address",
        "delivery_partner_id",
    )
    def _check_delivery_city_name(self):
        for record in self:
            if (
                record.is_delivery_location_different_from_recipient_address
                and record.delivery_partner_id
                and not record.delivery_city_name
            ):
                raise ValidationError(
                    _("O Nome do Município do Local de Entrega é obrigatório.")
                )

    delivery_state = fields.Char(
        compute="_compute_delivery_state",
        string="UF do Local de Entrega",
        store=True,
        size=2,
    )

    @api.depends(
        "delivery_partner_id",
        "delivery_partner_id.state_id",
        "delivery_partner_id.is_foreign",
    )
    def _compute_delivery_state(self):
        for record in self:
            if record.delivery_partner_id and record.delivery_partner_id.is_foreign:
                record.delivery_state = "EX"
            elif record.delivery_partner_id and record.delivery_partner_id.state_id:
                record.delivery_state = record.delivery_partner_id.state_id.code
            else:
                record.delivery_state = False

    @api.constrains(
        "delivery_state",
        "is_delivery_location_different_from_recipient_address",
        "delivery_partner_id",
    )
    def _check_delivery_state(self):
        for record in self:
            if (
                record.is_delivery_location_different_from_recipient_address
                and record.delivery_partner_id
                and not record.delivery_state
            ):
                raise ValidationError(_("A UF do Local de Entrega é obrigatória."))

    delivery_zip = fields.Char(
        compute="_compute_delivery_zip",
        string="CEP do Local de Entrega",
        store=True,
        readonly=True,
        size=8,
    )

    @api.depends("delivery_partner_id", "delivery_partner_id.unformatted_zip")
    def _compute_delivery_zip(self):
        for record in self:
            if (
                record.delivery_partner_id
                and record.delivery_partner_id.unformatted_zip
            ):
                record.delivery_zip = record.delivery_partner_id.unformatted_zip.zfill(
                    8
                )
            else:
                record.delivery_zip = False

    delivery_country_code = fields.Integer(
        related="delivery_partner_id.country_id.bacen_code",
        string="Código do País do Local de Entrega",
        store=True,
        readonly=True,
    )

    delivery_country_name = fields.Char(
        string="Nome do País do Local de Entrega",
        store=True,
        size=60,
        compute="_compute_delivery_country_name",
        readonly=True,
    )

    @api.depends("delivery_partner_id", "delivery_partner_id.country_id")
    def _compute_delivery_country_name(self):
        for record in self:
            if record.delivery_partner_id and record.delivery_partner_id.country_id:
                record.delivery_country_name = (
                    record.delivery_partner_id.country_id.with_context(
                        lang="pt_BR"
                    ).name
                )
            else:
                record.delivery_country_name = False

    delivery_formatted_phone = fields.Char(
        related="delivery_partner_id.phone",
        string="Telefone do Local de Entrega",
        store=True,
    )

    delivery_phone = fields.Char(
        compute="_compute_delivery_phone",
        string="Telefone do Local de Entrega",
        store=True,
    )

    @api.depends("delivery_formatted_phone")
    def _compute_delivery_phone(self):
        for record in self:
            if record.delivery_formatted_phone:
                record.delivery_phone = "".join(
                    filter(str.isdigit, record.delivery_formatted_phone)
                )
            else:
                record.delivery_phone = False

    delivery_email = fields.Char(
        related="delivery_partner_id.nfe_document_email",
        string="Email do Local de Entrega",
        store=True,
        size=60,
    )

    delivery_ie = fields.Char(
        related="delivery_partner_id.inscr_est",
        string="Inscrição Estadual do Local de Entrega",
        store=True,
        size=14,
        readonly=True,
    )

    # === Grupo GA. Autorização para obter XML  ===
    # autXML - Pessoas autorizadas a acessar o XML da NF-e
    authorized_xml_access_ids = fields.Many2many(
        comodel_name="res.partner",
        string="Pessoas Autorizadas a Acessar XML",
    )

    def validate_authorized_xml_access_ids(self, record):
        if len(record.authorized_xml_access_ids) > 10:
            raise ValidationError(
                _(
                    "O número máximo de pessoas autorizadas a acessar o XML da NF-e é 10."
                )
            )
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

    # @api.onchange("authorized_xml_access_ids")
    # def _onchange_authorized_xml_access_ids(self):
    #     for record in self:
    #         record.validate_authorized_xml_access_ids(record)

    @api.constrains("authorized_xml_access_ids")
    def _check_authorized_xml_access_ids(self):
        for record in self:
            record.validate_authorized_xml_access_ids(record)

    # === Grupo H. Detalhamento de Produtos e Serviços da NF-e  ===
    # det - Detalhamento de Produtos e Serviços. Múltiplas ocorrências (máximo = 990).

    invoice_line_ids = fields.One2many(
        comodel_name="l10n_br_nfe.nfe.document.line",
        inverse_name="nfe_id",
        string="Itens da Nota Fiscal",
        ondelete="cascade",
    )

    @api.constrains("invoice_line_ids")
    def _check_invoice_line_ids(self):
        for record in self:
            if len(record.invoice_line_ids) > 990:
                raise ValidationError(
                    _("O número máximo de itens da nota fiscal é 990.")
                )

    @api.onchange("invoice_line_ids", "invoice_line_ids.total_value")
    def _onchange_invoice_line_ids_redistribute_freight(self):
        """Redistribui o frete quando os itens da nota fiscal mudam."""
        for record in self:
            if record.total_freight:
                record.distribute_total_value(record.total_freight, "freight_value")

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

    # TODO verificar  se nao existem condicoes especificas de soma pro ICMS diferido
    @api.depends(
        "issuer_id",
        "issuer_id.fiscal_framework",
        "invoice_line_ids",
        "invoice_line_ids.icms_bc_value",
        "emission_finality",
    )
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

    @api.depends(
        "issuer_id",
        "issuer_id.fiscal_framework",
        "invoice_line_ids",
        "invoice_line_ids.icms_value",
        "emission_finality",
    )
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

    total_icms_deson = fields.Float(
        string="Valor ICMS Desonerado",
        digits=(13, 2),
        compute="_compute_total_icms_deson",
        store=True,
    )

    @api.depends("invoice_line_ids", "invoice_line_ids.icms_deson_value")
    def _compute_total_icms_deson(self):
        for record in self:
            record.total_icms_deson = sum(
                record.invoice_line_ids.mapped("icms_deson_value")
            )

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

    @api.depends(
        "issuer_id",
        "issuer_id.fiscal_framework",
        "invoice_line_ids",
        "invoice_line_ids.icms_fcp_value",
        "emission_finality",
    )
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

    @api.depends("invoice_line_ids", "invoice_line_ids.icms_st_bc_value")
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

    @api.depends("invoice_line_ids", "invoice_line_ids.icms_st_value")
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

    @api.depends("invoice_line_ids", "invoice_line_ids.icms_st_fcp_value")
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

    @api.depends("invoice_line_ids", "invoice_line_ids.icms_st_fcp_retention_value")
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

    @api.depends("invoice_line_ids", "invoice_line_ids.total_value")
    def _compute_total_products(self):
        for record in self:
            record.total_products = sum(record.invoice_line_ids.mapped("total_value"))

    def distribute_total_value(self, total_value_to_distribute, item_key):
        """Rateia o valor proporcionalmente entre os itens da nota fiscal."""
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

    # Valor Total do Frete.
    total_freight = fields.Float(
        string="Valor Total do Frete",
        digits=(13, 2),
        compute="_compute_total_freight",
        store=True,
        readonly=False,
    )

    @api.depends("invoice_line_ids", "invoice_line_ids.freight_value")
    def _compute_total_freight(self):
        for record in self:
            record.total_freight = sum(record.invoice_line_ids.mapped("freight_value"))

    @api.onchange("total_freight")
    def _onchange_total_freight(self):
        for record in self:
            items_freight_sum = sum(record.invoice_line_ids.mapped("freight_value"))
            # Se o total_freight é igual à soma dos valores do frete dos itens,
            # significa que a mudança veio de um item sendo editado, não do usuário
            # editando diretamente o campo total_freight. Neste caso, não redistribuir.
            if abs((record.total_freight or 0) - items_freight_sum) < 0.01:
                return

            record.distribute_total_value(record.total_freight, "freight_value")

    # Valor Total do Seguro.
    total_insurance = fields.Float(
        string="Valor Total do Seguro",
        digits=(13, 2),
        compute="_compute_total_insurance",
        store=True,
        readonly=False,
    )

    @api.depends("invoice_line_ids", "invoice_line_ids.insurance_value")
    def _compute_total_insurance(self):
        for record in self:
            record.total_insurance = sum(
                record.invoice_line_ids.mapped("insurance_value")
            )

    @api.onchange("total_insurance")
    def _onchange_total_insurance(self):
        for record in self:

            items_insurance_sum = sum(record.invoice_line_ids.mapped("insurance_value"))
            # Se o total_insurance é igual à soma dos valores do seguro dos itens,
            # significa que a mudança veio de um item sendo editado, não do usuário
            # editando diretamente o campo total_insurance. Neste caso, não redistribuir.
            if abs((record.total_insurance or 0) - items_insurance_sum) < 0.01:
                return

            record.distribute_total_value(record.total_insurance, "insurance_value")

    # Valor Total do Desconto.
    total_discount = fields.Float(
        string="Valor Total do Desconto",
        digits=(13, 2),
        compute="_compute_total_discount",
        store=True,
        readonly=False,
    )

    @api.depends("invoice_line_ids", "invoice_line_ids.discount_value")
    def _compute_total_discount(self):
        for record in self:
            record.total_discount = sum(
                record.invoice_line_ids.mapped("discount_value")
            )

    @api.onchange("total_discount")
    def _onchange_total_discount(self):
        """Distribui o desconto total entre os itens da nota fiscal."""
        for record in self:
            items_discount_sum = sum(record.invoice_line_ids.mapped("discount_value"))

            # Se o total_discount é igual à soma dos descontos dos itens,
            # significa que a mudança veio de um item sendo editado, não do usuário
            # editando diretamente o campo total_discount. Neste caso, não redistribuir.
            if abs((self.total_discount or 0) - items_discount_sum) < 0.01:
                continue

            record.distribute_total_value(record.total_discount, "discount_value")
            for line in record.invoice_line_ids:
                unit_discount = (
                    line.discount_value / line.quantity if line.quantity else 0
                )
                line.with_context(skip_discount_compute=True).write(
                    {
                        "unit_discount_value": unit_discount,
                        "unit_discount_percent": (
                            unit_discount / line.unit_price * 100
                            if line.unit_price
                            else 0
                        ),
                    }
                )

    # Valor Total do Imposto de Importação.
    total_ii = fields.Float(
        string="Valor Total do Imposto de Importação",
        digits=(13, 2),
        compute="_compute_total_ii",
        store=True,
        readonly=True,
    )

    @api.depends("invoice_line_ids", "invoice_line_ids.ii_value")
    def _compute_total_ii(self):
        for record in self:
            record.total_ii = sum(record.invoice_line_ids.mapped("ii_value"))

    total_ipi = fields.Float(
        string="Valor Total do IPI",
        digits=(13, 2),
        compute="_compute_total_ipi",
        store=True,
        readonly=True,
    )
    # Valor Total do IPI.

    @api.depends(
        "issuer_id",
        "issuer_id.fiscal_framework",
        "invoice_line_ids",
        "invoice_line_ids.ipi_value",
        "emission_finality",
    )
    def _compute_total_ipi(self):
        for record in self:
            total_ipi = sum(record.invoice_line_ids.mapped("ipi_value"))

            if (
                record._is_issuer_simples_nacional()
                and record.emission_finality in ["1", "2", "3"]
                and not total_ipi == 0.00
            ):
                raise ValidationError(
                    _(
                        "A soma do valor do IPI deve ser zero para nota fiscal"
                        " normal emitida por empresa do Simples Nacional."
                    )
                )
            elif record.emission_finality == "4":
                items_with_non_zero_ipi = []
                for line in record.invoice_line_ids:
                    if line.ipi_value > 0:
                        items_with_non_zero_ipi.append(line)
                raise ValidationError(
                    _(
                        "Para nota fiscal de devolução, o valor do IPI deve "
                        "ser informado no campo 'Valor Total do IPI Devolvido'. "
                        "Itens informados com IPI: "
                        + ", ".join(item.name for item in items_with_non_zero_ipi)
                    )
                )
            else:
                record.total_ipi = sum(record.invoice_line_ids.mapped("ipi_value"))

    # Valor Total do IPI Devolvido.
    total_ipi_returned = fields.Float(
        string="Valor Total do IPI Devolvido",
        digits=(13, 2),
        compute="_compute_total_ipi_returned",
        store=True,
        readonly=True,
    )

    @api.depends(
        "invoice_line_ids", "invoice_line_ids.total_ipi_returned", "emission_finality"
    )
    def _compute_total_ipi_returned(self):
        for record in self:
            total_ipi_returned = sum(
                record.invoice_line_ids.mapped("total_ipi_returned")
            )

            if total_ipi_returned > 0.00 and record.emission_finality != "4":
                items_with_non_zero_ipi_returned = []
                for line in record.invoice_line_ids:
                    if line.total_ipi_returned > 0:
                        items_with_non_zero_ipi_returned.append(line)
                raise ValidationError(
                    _(
                        "O valor do IPI devolvido deve ser zero para nota fiscal"
                        " normal emitida, exceto para nota fiscal de devolução."
                        "Itens informados com IPI devolvido: "
                        + ", ".join(
                            item.name for item in items_with_non_zero_ipi_returned
                        )
                    )
                )
            else:
                record.total_ipi_returned = total_ipi_returned

    total_pis = fields.Float(
        string="Valor Total do PIS",
        digits=(13, 2),
        compute="_compute_total_pis",
        store=True,
        readonly=True,
    )
    # Valor Total do PIS.

    @api.depends(
        "issuer_id",
        "issuer_id.fiscal_framework",
        "invoice_line_ids",
        "invoice_line_ids.pis_value",
        "emission_finality",
    )
    def _compute_total_pis(self):
        for record in self:
            total_pis = sum(record.invoice_line_ids.mapped("pis_value"))
            if (
                record._is_issuer_simples_nacional()
                and record.emission_finality == "1"
                and not total_pis == 0.00
            ):
                raise ValidationError(
                    _(
                        "A soma do valor do PIS deve ser zero para nota fiscal"
                        " normal emitida por empresa do Simples Nacional."
                    )
                )
            else:
                record.total_pis = total_pis

    total_cofins = fields.Float(
        string="Valor Total da COFINS",
        digits=(13, 2),
        compute="_compute_total_cofins",
        store=True,
        readonly=True,
    )
    # Valor Total da COFINS.

    @api.depends(
        "issuer_id",
        "issuer_id.fiscal_framework",
        "invoice_line_ids",
        "invoice_line_ids.cofins_value",
        "emission_finality",
    )
    def _compute_total_cofins(self):
        for record in self:
            total_cofins = sum(record.invoice_line_ids.mapped("cofins_value"))
            if (
                record._is_issuer_simples_nacional()
                and record.emission_finality == "1"
                and not total_cofins == 0.00
            ):
                raise ValidationError(
                    _(
                        "A soma do valor da COFINS deve ser zero para nota fiscal"
                        " normal emitida por empresa do Simples Nacional."
                    )
                )
            else:
                record.total_cofins = total_cofins

    # Outras Despesas acessórias.
    total_other_expenses = fields.Float(
        string="Outras Despesas Acessórias",
        digits=(13, 2),
        compute="_compute_total_other_expenses",
        store=True,
        readonly=False,
    )

    @api.depends("invoice_line_ids", "invoice_line_ids.other_expenses_value")
    def _compute_total_other_expenses(self):
        for record in self:
            record.total_other_expenses = sum(
                record.invoice_line_ids.mapped("other_expenses_value")
            )

    @api.onchange("total_other_expenses")
    def _onchange_total_other_expenses(self):
        for record in self:

            items_other_expenses_sum = sum(
                record.invoice_line_ids.mapped("other_expenses_value")
            )
            # Se o total_other_expenses é igual à soma dos valores das outras despesas acessórias dos itens,
            # significa que a mudança veio de um item sendo editado, não do usuário
            # editando diretamente o campo total_other_expenses. Neste caso, não redistribuir.
            if (
                abs((record.total_other_expenses or 0) - items_other_expenses_sum)
                < 0.01
            ):
                return

            record.distribute_total_value(
                record.total_other_expenses, "other_expenses_value"
            )

    # Valor Total da NF-e.
    total_nfe = fields.Float(
        string="Valor Total da NF-e",
        required=True,
        digits=(13, 2),
        compute="_compute_total_nfe",
    )

    @api.depends(
        "invoice_line_ids",
        "total_products",
        "total_discount",
        "total_icms_deson",
        "total_icms_st_value",
        "total_icms_st_fcp",
        "total_freight",
        "total_insurance",
        "total_other_expenses",
        "total_ii",
        "total_ipi",
        "total_ipi_returned",
    )
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

    # -Total do vNF (id:W16)
    # (+) vProd (id:W07)
    # (-) vDesc (id:W10)
    # (-) vICMSDeson (id:W04a)
    # (+) vST (id:W06)
    # (+) vFCPST (id:W06a)
    # (+) vFrete (id:W08)
    # (+) vSeg (id:W09)
    # (+) vOutro (id:W15)
    # (+) vII (id:W11)
    # (+) vIPI (id:W12)
    # (+) vIPIDevol (id: W12a)
    # (+) vServ (id:W18) (*3) (NT 2011/005)

    total_approx_taxes_federal = fields.Float(
        string="Valor Aproximado dos Tributos Federais",
        digits=(13, 2),
        compute="_compute_total_approx_taxes_federal",
        store=True,
    )

    @api.depends("invoice_line_ids", "invoice_line_ids.approximate_federal_tax_amount")
    def _compute_total_approx_taxes_federal(self):
        for record in self:
            record.total_approx_taxes_federal = sum(
                record.invoice_line_ids.mapped("approximate_federal_tax_amount")
            )

    total_approx_taxes_state = fields.Float(
        string="Valor Aproximado dos Tributos Estaduais",
        digits=(13, 2),
        compute="_compute_total_approx_taxes_state",
        store=True,
    )

    @api.depends("invoice_line_ids", "invoice_line_ids.approximate_state_tax_amount")
    def _compute_total_approx_taxes_state(self):
        for record in self:
            record.total_approx_taxes_state = sum(
                record.invoice_line_ids.mapped("approximate_state_tax_amount")
            )

    total_approx_taxes_municipal = fields.Float(
        string="Valor Aproximado dos Tributos Municipais",
        digits=(13, 2),
        compute="_compute_total_approx_taxes_municipal",
        store=True,
    )

    @api.depends(
        "invoice_line_ids", "invoice_line_ids.approximate_municipal_tax_amount"
    )
    def _compute_total_approx_taxes_municipal(self):
        for record in self:
            record.total_approx_taxes_municipal = sum(
                record.invoice_line_ids.mapped("approximate_municipal_tax_amount")
            )

    total_approx_taxes = fields.Float(
        string="Valor Aproximado dos Tributos",
        digits=(13, 2),
        compute="_compute_total_approx_taxes",
        store=True,
    )
    # Total do valor aproximado dos tributos. Opcional. [227, 228]

    @api.depends(
        "invoice_line_ids",
        "total_approx_taxes_federal",
        "total_approx_taxes_state",
        "total_approx_taxes_municipal",
    )
    def _compute_total_approx_taxes(self):
        for record in self:
            record.total_approx_taxes = sum(
                record.invoice_line_ids.mapped("approximate_tax_amount")
            )

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

    freight_info_enabled = fields.Boolean(
        string="Informações de Frete Habilitado",
        compute="_compute_freight_info_enabled",
        store=False,
    )

    @api.depends("freight_modality")
    def _compute_freight_info_enabled(self):
        for record in self:
            record.freight_info_enabled = record.freight_modality != "9"

    freight_partner_id = fields.Many2one(
        comodel_name="res.partner",
        string="Transportadora",
        domain="[('country_id.code', '=', 'BR'), ('is_freight_carrier', '=', True)]",
        help="Transportadora responsável pelo frete.",
    )

    freight_carrier_cnpj = fields.Char(
        compute="_compute_freight_carrier_cnpj",
        string="CNPJ da Transportadora",
        store=True,
        size=14,
        readonly=True,
    )

    @api.depends(
        "freight_partner_id",
        "freight_partner_id.vat",
        "freight_partner_id.company_type",
    )
    def _compute_freight_carrier_cnpj(self):
        for record in self:
            if (
                record.freight_partner_id
                and record.freight_partner_id.company_type == "company"
                and record.freight_partner_id.vat
                and len(record.freight_partner_id.vat) == 14
            ):
                record.freight_carrier_cnpj = record.freight_partner_id.vat
            else:
                record.freight_carrier_cnpj = False

    freight_carrier_cpf = fields.Char(
        compute="_compute_freight_carrier_cpf",
        string="CPF da Transportadora",
        store=True,
        size=11,
        readonly=True,
    )

    @api.depends(
        "freight_partner_id",
        "freight_partner_id.vat",
        "freight_partner_id.company_type",
    )
    def _compute_freight_carrier_cpf(self):
        for record in self:
            if (
                record.freight_partner_id
                and record.freight_partner_id.company_type == "person"
                and record.freight_partner_id.vat
                and len(record.freight_partner_id.vat) == 11
            ):
                record.freight_carrier_cpf = record.freight_partner_id.vat
            else:
                record.freight_carrier_cpf = False

    @api.constrains("freight_carrier_cnpj", "freight_carrier_cpf")
    def _check_freight_carrier_cnpj_cpf(self):
        for record in self:
            if record.freight_partner_id:
                if record.freight_partner_id.is_foreign:
                    continue
                elif (
                    record.freight_partner_id.company_type == "company"
                    and not record.freight_carrier_cnpj
                ):
                    raise ValidationError(_("O CNPJ da Transportadora é obrigatório."))
                elif (
                    record.freight_partner_id.company_type == "person"
                    and not record.freight_carrier_cpf
                ):
                    raise ValidationError(_("O CPF da Transportadora é obrigatório."))

    freight_carrier_legal_name = fields.Char(
        related="freight_partner_id.legal_name",
        string="Razão Social da Transportadora",
        store=True,
        size=60,
        readonly=True,
    )

    @api.constrains("freight_carrier_legal_name")
    def _check_freight_carrier_legal_name(self):
        for record in self:
            if record.freight_partner_id and not record.freight_carrier_legal_name:
                raise ValidationError(
                    _("A Razão Social da Transportadora é obrigatória.")
                )

    # Literal “ISENTO” para transportador isento de inscrição no cadastro de contribuintes ICMS;
    freight_carrier_ie = fields.Char(
        related="freight_partner_id.inscr_est",
        string="Inscrição Estadual da Transportadora",
        size=14,
        readonly=True,
        store=True,
        compute="_compute_freight_carrier_ie",
    )

    @api.depends("freight_partner_id.no_inscr_est", "freight_partner_id.inscr_est")
    def _compute_freight_carrier_ie(self):
        if self.freight_partner_id.no_inscr_est:
            self.freight_carrier_ie = "ISENTO"
        elif self.freight_partner_id.inscr_est:
            self.freight_carrier_ie = self.freight_partner_id.inscr_est
        else:
            self.freight_carrier_ie = False

    freight_carrier_address = fields.Char(
        compute="_compute_freight_carrier_address",
        string="Endereço da Transportadora",
        store=True,
        size=60,
        readonly=True,
    )

    @api.depends(
        "freight_partner_id",
        "freight_partner_id.street",
        "freight_partner_id.street_number",
        "freight_partner_id.street_complement",
    )
    def _compute_freight_carrier_address(self):
        for record in self:
            if record.freight_partner_id:
                record.freight_carrier_address = format_partner_address(
                    record.freight_partner_id.street,
                    record.freight_partner_id.street_number,
                    record.freight_partner_id.street_complement,
                )
            else:
                record.freight_carrier_address = False

    freight_carrier_city_name = fields.Char(
        related="freight_partner_id.city_id.name",
        string="Cidade",
        store=True,
        translate=True,
        size=60,
        readonly=True,
    )

    freight_carrier_state = fields.Char(
        related="freight_partner_id.state_id.code",
        string="UF",
        store=True,
        size=2,
        readonly=True,
    )

    @api.constrains("freight_carrier_state", "freight_carrier_ie")
    def _check_freight_carrier_state_ie(self):
        for record in self:
            if record.freight_partner_id:
                if record.freight_carrier_ie and not record.freight_carrier_state:
                    raise ValidationError(
                        _(
                            "A UF da Transportadora é obrigatória quando a Inscrição Estadual é informada ou for isenta."
                        )
                    )

    freight_carrier_vehicle_id = fields.Many2one(
        comodel_name="l10n_br_fiscal.freight.carrier.vehicle",
        string="Veículo de transporte",
        domain="[('partner_id', '=', freight_partner_id ), ('traction', '=', True)]",
        help="Veículo de transporte responsável pelo frete.",
    )

    freight_carrier_vehicle_license_plate = fields.Char(
        related="freight_carrier_vehicle_id.license_plate",
        string="Placa do veículo de transporte",
        store=True,
        readonly=True,
    )

    freight_carrier_vehicle_licence_plate_state_code = fields.Char(
        related="freight_carrier_vehicle_id.licence_plate_state_id.code",
        string="Estado da placa do veículo de transporte",
        store=True,
        readonly=True,
    )

    freight_carrier_vehicle_rntrc = fields.Char(
        related="freight_carrier_vehicle_id.rntrc",
        string="RNTRC do veículo de transporte",
        store=True,
        readonly=True,
    )

    freight_carrier_trailers_ids = fields.One2many(
        comodel_name="l10n_br_nfe.nfe.document.vehicle.traillers",
        inverse_name="nfe_document_id",
        string="Reboques do veículo de transporte",
    )

    # X26 - Grupo Volumes (0-5000)
    carrier_volume_ids = fields.One2many(
        comodel_name="l10n_br_nfe.nfe.carrier.volume",
        inverse_name="nfe_document_id",
        string="Volumes Transportados",
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

    def _compute_billing_original_value(self):
        for record in self:
            record.billing_original_value = 0.00

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
            ) - sum(record.payment_detail_ids.mapped("change_value")):
                raise ValidationError(
                    _(
                        "O valor total da NF-e deve ser igual ao valor total dos pagamentos menos o valor do troco."
                    )
                )

    # === Grupo YB. Informações do Intermediador da Transação ===

    is_marketplace_transaction = fields.Boolean(
        string="É transação com Marketplace",
        compute="_compute_is_marketplace_transaction",
        store=True,
    )

    @api.depends("intermediator_indicator")
    def _compute_is_marketplace_transaction(self):
        for record in self:
            record.is_marketplace_transaction = (
                True if record.intermediator_indicator == "1" else False
            )

    @api.onchange("intermediator_indicator")
    def _onchange_intermediator_indicator(self):
        for record in self:
            if record.intermediator_indicator != "1":
                record.marketplace_id = False

    marketplace_id = fields.Many2one(
        comodel_name="l10n_br_nfe.company.marketplace",
        string="Marketplace",
        domain="[('company_id', '=', company_id)]",
    )

    marketplace_username = fields.Char(
        related="marketplace_id.marketplace_username",
        string="Usuário do Marketplace",
        store=True,
        readonly=True,
    )

    marketplace_cnpj = fields.Char(
        related="marketplace_id.provider_id.vat",
        string="CNPJ do Marketplace",
        store=True,
        readonly=True,
    )

    @api.constrains("marketplace_id", "is_marketplace_transaction")
    def _check_marketplace_id(self):
        for record in self:
            if record.is_marketplace_transaction and not record.marketplace_id:
                raise ValidationError(
                    "O Marketplace é obrigatório para transações com Marketplace."
                )
            if record.marketplace_id:
                if (
                    not record.marketplace_id.provider_id.vat
                    or len(record.marketplace_id.provider_id.vat) != 14
                ):
                    raise ValidationError(
                        "O CNPJ do Marketplace é obrigatório e deve ter 14 caracteres."
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

    issuer_additional_information = fields.Text(
        string="Informações Adicionais", size=5000
    )

    ibpt_keys = fields.Text(
        string="Chaves do IBPT",
        compute="_compute_ibpt_keys",
        store=True,
    )

    @api.depends("invoice_line_ids", "invoice_line_ids.ibpt_key")
    def _compute_ibpt_keys(self):
        for record in self:
            ibpt_keys = set(record.invoice_line_ids.mapped("ibpt_key"))
            record.ibpt_keys = ", ".join(key for key in ibpt_keys if key)

    total_approx_taxes_information = fields.Text(
        string="Informações sobre os Tributos Aproximados",
        compute="_compute_total_approx_taxes_information",
        store=True,
    )

    @api.depends(
        "total_approx_taxes_federal",
        "total_approx_taxes_state",
        "total_approx_taxes_municipal",
        "ibpt_keys",
    )
    def _compute_total_approx_taxes_information(self):
        for record in self:
            record.total_approx_taxes_information = f"Trib aprox R$ {format_number(record.total_approx_taxes_federal)} Fed, R$ {format_number(record.total_approx_taxes_state)} Est e R$ {format_number(record.total_approx_taxes_municipal)} Mun \nFonte: IBPT {record.ibpt_keys}"

    mandatory_additional_information = fields.Text(
        string="Informações Adicionais Obrigatórias",
        compute="_compute_mandatory_additional_information",
        store=True,
    )

    @api.depends(
        "mandatory_additional_information_ids", "total_approx_taxes_information"
    )
    def _compute_mandatory_additional_information(self):
        for record in self:
            # Filter out empty/False values
            info_values = record.mandatory_additional_information_ids.mapped(
                "additional_information"
            )
            info_values.append(record.total_approx_taxes_information)
            # Join only non-empty strings
            record.mandatory_additional_information = "\n".join(
                filter(None, info_values)
            )

    # Grupo ZD. Informações do Responsável Técnico (NT 2018.005)

    tech_contact_id = fields.Many2one(
        comodel_name="l10n_br_nfe.nfe.tech.contact",
        string="Responsável Técnico",
        compute="_compute_tech_contact_id",
        store=True,
        readonly=True,
    )

    @api.depends("company_id")
    def _compute_tech_contact_id(self):
        for record in self:
            record.tech_contact_id = record.company_id.tech_contact_id

    tech_contact_name = fields.Char(
        related="tech_contact_id.name",
        string="Nome do Responsável Técnico",
        store=True,
        readonly=True,
    )

    tech_contact_cnpj = fields.Char(
        related="tech_contact_id.cnpj",
        string="CNPJ do Responsável Técnico",
        store=True,
        readonly=True,
    )

    @api.constrains("tech_contact_id", "tech_contact_cnpj")
    def _check_tech_contact_cnpj(self):
        for record in self:
            if record.tech_contact_id and not record.tech_contact_cnpj:
                raise ValidationError(
                    f"Nenhum CNPJ configurado para o responsável técnico {record.tech_contact_id.name}."
                    "Configure um CNPJ nas configurações do responsável técnico."
                )

    tech_contact_phone = fields.Char(
        string="Telefone do Responsável Técnico",
        store=True,
        readonly=True,
        compute="_compute_tech_contact_phone",
    )

    @api.depends("tech_contact_id.phone")
    def _compute_tech_contact_phone(self):
        for record in self:
            if record.tech_contact_id and record.tech_contact_id.phone:
                record.tech_contact_phone = "".join(
                    c for c in record.tech_contact_id.phone if c.isdigit()
                )
            else:
                record.tech_contact_phone = False

    @api.constrains("tech_contact_id", "tech_contact_phone")
    def _check_tech_contact_phone(self):
        for record in self:
            if record.tech_contact_id and not record.tech_contact_phone:
                raise ValidationError(
                    f"Nenhum telefone configurado para o responsável técnico {record.tech_contact_id.name}."
                    "Configure um telefone nas configurações do responsável técnico."
                )

    tech_contact_email = fields.Char(
        related="tech_contact_id.email",
        string="Email do Responsável Técnico",
        store=True,
        readonly=True,
    )

    @api.constrains("tech_contact_id", "tech_contact_email")
    def _check_tech_contact_email(self):
        for record in self:
            if record.tech_contact_id and not record.tech_contact_email:
                raise ValidationError(
                    f"Nenhum email configurado para o responsável técnico {record.tech_contact_id.name}."
                    "Configure um email nas configurações do responsável técnico."
                )

    tech_contact_csrt_identifier = fields.Char(
        related="tech_contact_id.csrt_identifier",
        string="CSRT do Responsável Técnico",
        readonly=True,
    )

    tech_contact_csrt_hash = fields.Char(
        related="tech_contact_id.csrt_hash",
        string="Hash CSRT do Responsável Técnico",
        readonly=True,
    )

    @api.constrains(
        "tech_contact_csrt_identifier", "tech_contact_id", "tech_contact_csrt_hash"
    )
    def _check_tech_contact_csrt_identifier(self):
        for record in self:
            if not record.tech_contact_id:
                return

            csrt_fields = [
                "tech_contact_csrt_identifier",
                "tech_contact_csrt_hash",
            ]

            if any(csrt_fields) and not all(csrt_fields):
                raise ValidationError(
                    f"Nenhum CSRT configurado para o responsável técnico {record.tech_contact_id.name}."
                    f"Configure um CSRT nas configurações do responsável técnico."
                )

    qr_code = fields.Text(string="QR Code", size=600)

    # Campos para armazenar XML assinado
    xml_signed = fields.Binary(
        string="XML Assinado",
        attachment=True,
        help="XML da NF-e com assinatura digital",
    )

    xml_signed_filename = fields.Char(
        string="Nome do Arquivo XML",
        compute="_compute_xml_signed_filename",
        store=True,
    )

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

    @api.depends("access_key")
    def _compute_xml_signed_filename(self):
        """Computa o nome do arquivo XML baseado na chave de acesso"""
        for record in self:
            if record.access_key:
                record.xml_signed_filename = f"{record.access_key}-nfe.xml"
            else:
                record.xml_signed_filename = "nfe.xml"

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

    issuer_additional_information = fields.Text(
        string="Informações Adicionais do Emitente",
        size=5000,
        help="Informações adicionais de interesse do contribuinte. ",
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

    def _sign_nfe_xml(self, xml_element):
        """
        Assina o XML da NF-e usando o certificado digital A1 da empresa.

        Args:
            xml_element: Elemento lxml.etree contendo o XML da NF-e

        Returns:
            String contendo o XML assinado

        Raises:
            ValidationError: Se não houver certificado válido ou erro na assinatura
        """
        self.ensure_one()

        # Validar se existe certificado configurado na empresa
        if not self.company_id.certificate_nfe_id:
            raise ValidationError(
                _(
                    "Nenhum certificado NF-e configurado para a empresa %s. "
                    "Configure um certificado A1 nas configurações da empresa."
                )
                % self.company_id.name
            )

        certificate = self.company_id.certificate_nfe_id

        # Validar se o certificado está válido
        if not certificate.is_valid:
            raise ValidationError(
                _("O certificado NF-e da empresa %s está expirado. " "Validade: %s")
                % (self.company_id.name, certificate.date_expiration)
            )

        try:
            cert = self.company_id.get_nfe_certificate()
            assinador = Assinatura(cert)

            reference = f"NFe{self.access_key}"
            xml_signed = assinador.assina_xml2(xml_element, reference)

            # signxml inserts line breaks/spaces in base64 fields — SEFAZ rejects that
            signed_tree = etree.fromstring(
                xml_signed.encode("utf-8")
                if isinstance(xml_signed, str)
                else xml_signed
            )
            ns = {"ds": "http://www.w3.org/2000/09/xmldsig#"}
            for tag in ("ds:SignatureValue", "ds:DigestValue", "ds:X509Certificate"):
                for elem in signed_tree.findall(f".//{tag}", ns):
                    if elem.text:
                        elem.text = (
                            elem.text.replace("\n", "")
                            .replace("\r", "")
                            .replace(" ", "")
                        )

            return etree.tostring(signed_tree, encoding="unicode")

        except Exception as e:
            raise ValidationError(_("Erro ao assinar XML da NF-e: %s") % str(e))

    def action_generate_nfe(self):
        """
        Gera e assina o XML da NF-e.
        O XML assinado é armazenado no campo xml_signed.
        """
        self.ensure_one()

        # Fetch IBPT taxes for all lines before generating NFe
        self._fetch_all_ibpt_taxes()

        # Gerar XML da NF-e
        root = buildNfeXmlFromNfeDocumentModel(self)

        # Assinar o XML
        xml_signed_string = self._sign_nfe_xml(root)

        # Validar XML assinado contra o XSD oficial (Signature é obrigatório no schema)
        signed_tree = etree.fromstring(xml_signed_string.encode("utf-8"))
        validate_nfe_xml(signed_tree, version=self.nfe_version)

        # Converter para base64 e salvar no campo
        xml_signed_base64 = base64.b64encode(xml_signed_string.encode("utf-8"))
        self.write(
            {
                "xml_signed": xml_signed_base64,
            }
        )

        # Imprimir XML assinado para debug (opcional)
        print("XML da NF-e gerado e assinado com sucesso!")
        print(xml_signed_string)

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Sucesso"),
                "message": _("XML da NF-e gerado e assinado com sucesso!"),
                "type": "success",
                "sticky": False,
            },
        }

    def _fetch_all_ibpt_taxes(self):
        """
        Internal method to fetch IBPT taxes for all lines.
        Returns a list of errors (empty if all succeeded).
        Does not raise exceptions - errors are collected and returned.
        """
        self.ensure_one()
        errors = []

        for line in self.invoice_line_ids:
            try:
                line._fetch_ibpt_taxes()
            except UserError as e:
                errors.append(
                    f"{line.product_description or line.product_id.name}: {e.args[0]}"
                )

        return errors

    def action_fetch_all_ibpt_taxes(self):
        """
        Fetch IBPT taxes for all lines in the document.
        Shows warnings for lines that failed but doesn't block the operation.
        """
        errors = self._fetch_all_ibpt_taxes()

        if errors:
            # Show warning with list of failed lines
            error_message = _(
                "Os seguintes itens não puderam ter os tributos IBPT atualizados:\n\n"
            )
            error_message += "\n".join(f"• {err}" for err in errors)
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": _("IBPT - Avisos"),
                    "message": error_message,
                    "type": "warning",
                    "sticky": True,
                },
            }

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("IBPT"),
                "message": _(
                    "Tributos aproximados atualizados com sucesso para todos os itens!"
                ),
                "type": "success",
                "sticky": False,
                "next": {"type": "ir.actions.client", "tag": "reload"},
            },
        }
