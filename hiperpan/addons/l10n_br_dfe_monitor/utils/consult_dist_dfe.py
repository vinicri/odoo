from odoo.exceptions import UserError
from odoo import _
from erpbrasil.base.fiscal import cnpj_cpf
from lxml import etree
from .schema_validator import validate_dfe_xml
import logging
import tempfile
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    PrivateFormat,
    NoEncryption,
    pkcs12,
)
import base64
import os
import requests
import gzip

_logger = logging.getLogger(__name__)

# URL do Ambiente Nacional para NFeDistribuicaoDFe
NFE_DIST_DFE_URLS = {
    "production": "https://www1.nfe.fazenda.gov.br/NFeDistribuicaoDFe/NFeDistribuicaoDFe.asmx",
    "homologation": "https://hom1.nfe.fazenda.gov.br/NFeDistribuicaoDFe/NFeDistribuicaoDFe.asmx",
}


def _parse_dist_dfe_response(response_text):
    try:
        root = etree.fromstring(response_text.encode("utf-8"))
        namespaces = {
            "soap": "http://www.w3.org/2003/05/soap-envelope",
            "wsdl": "http://www.portalfiscal.inf.br/nfe/wsdl/NFeDistribuicaoDFe",
            "nfe": "http://www.portalfiscal.inf.br/nfe",
        }

        ret = root.xpath("//nfe:retDistDFeInt", namespaces=namespaces)

        if not ret:
            _logger.error("Elemento retDistDFeInt não encontrado na resposta")
            _logger.debug(f"Resposta XML:\n{response_text[:2000]}")
            raise UserError(
                _("Resposta inválida da SEFAZ: retDistDFeInt não encontrado")
            )

        # xpath returns a list; downstream code expects a single Element
        ret = ret[0]

        def find_text(element, tag):
            el = element.find(f"nfe:{tag}", namespaces) or element.find(
                f".//{{{namespaces['nfe']}}}{tag}"
            )
            return el.text if el is not None else None

        c_stat = find_text(ret, "cStat")
        x_motivo = find_text(ret, "xMotivo")
        ult_nsu = find_text(ret, "ultNSU")
        max_nsu = find_text(ret, "maxNSU")

        _logger.info(
            f"NFeDistribuicaoDFe - cStat={c_stat} xMotivo={x_motivo} ultNSU={ult_nsu} maxNSU={max_nsu}"
        )

        # Códigos de sucesso: 137=Nenhum documento, 138=Documento(s) localizado(s)
        if c_stat not in ("137", "138"):
            raise UserError(_("SEFAZ retornou erro: %s - %s") % (c_stat, x_motivo))

        documents = []
        lote = ret.find("nfe:loteDistDFeInt", namespaces) or ret.find(
            f".//{{{namespaces['nfe']}}}loteDistDFeInt"
        )

        if lote is not None:
            for doc_zip in lote.findall("nfe:docZip", namespaces) or lote.findall(
                f".//{{{namespaces['nfe']}}}docZip"
            ):
                nsu_attr = doc_zip.get("NSU")
                schema_attr = doc_zip.get("schema")
                compressed = doc_zip.text

                if not compressed:
                    continue

                # Descompactar conteúdo gzip em base64
                try:
                    raw = base64.b64decode(compressed)
                    xml_bytes = gzip.decompress(raw)
                    xml_str = xml_bytes.decode("utf-8")
                except Exception as e:
                    _logger.warning(f"Erro ao descompactar docZip NSU={nsu_attr}: {e}")
                    raise UserError(f"Erro ao descompactar docZip NSU={nsu_attr}: {e}")

                documents.append(
                    {
                        "nsu": nsu_attr,
                        "schema": schema_attr,
                        "xml": xml_str,
                    }
                )

        return {
            "c_stat": c_stat,
            "x_motivo": x_motivo,
            "ult_nsu": ult_nsu,
            "max_nsu": max_nsu,
            "documents": documents,
        }

    except etree.XMLSyntaxError as e:
        _logger.error(f"Erro de sintaxe XML na resposta: {e}")
        raise UserError(_("Erro ao processar resposta da SEFAZ: XML inválido"))
    except UserError:
        raise
    except Exception as e:
        _logger.error(
            f"Erro ao fazer parse da resposta NFeDistribuicaoDFe: {e}",
            exc_info=True,
        )
        raise


def _send_soap_request(url, xml_content, certificate):
    """
    Envia requisição SOAP para o Ambiente Nacional NFeDistribuicaoDFe
    """
    try:
        cert_bytes = base64.b64decode(certificate["cert_file"])
        private_key, certificate, _ = pkcs12.load_key_and_certificates(
            cert_bytes, certificate["password"].encode("utf-8")
        )
        key_pem = private_key.private_bytes(
            encoding=Encoding.PEM,
            format=PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=NoEncryption(),
        )
        cert_pem = certificate.public_bytes(Encoding.PEM)
    except Exception as e:
        _logger.error(f"Erro ao processar certificado: {e}")
        raise UserError(_("Erro ao processar certificado digital: %s") % str(e))

    with tempfile.NamedTemporaryFile(mode="wb", delete=False, suffix=".pem") as cf:
        cf.write(cert_pem)
        cert_path = cf.name

    with tempfile.NamedTemporaryFile(mode="wb", delete=False, suffix=".key") as kf:
        kf.write(key_pem)
        key_path = kf.name

    try:
        soap_env = f"""<?xml version="1.0" encoding="utf-8"?>
<soap12:Envelope xmlns:soap12="http://www.w3.org/2003/05/soap-envelope"
                 xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
                 xmlns:xsd="http://www.w3.org/2001/XMLSchema">
  <soap12:Body>
    <nfeDistDFeInteresse xmlns="http://www.portalfiscal.inf.br/nfe/wsdl/NFeDistribuicaoDFe">
      <nfeDadosMsg>
{xml_content}
      </nfeDadosMsg>
    </nfeDistDFeInteresse>
  </soap12:Body>
</soap12:Envelope>"""

        headers = {"Content-Type": "application/soap+xml; charset=utf-8"}

        _logger.info(f"Enviando consulta NFeDistribuicaoDFe para {url}")

        response = requests.post(
            url,
            data=soap_env.encode("utf-8"),
            headers=headers,
            cert=(cert_path, key_path),
            timeout=60,
        )

        _logger.info(f"Resposta recebida - Status: {response.status_code}")

        if response.status_code != 200:
            _logger.error(f"Erro HTTP: {response.status_code} - {response.text[:500]}")
            raise UserError(
                _("Erro ao consultar SEFAZ: HTTP %s") % response.status_code
            )

        return response

    finally:
        try:
            os.unlink(cert_path)
            os.unlink(key_path)
        except Exception as e:
            _logger.warning(f"Erro ao remover arquivos temporários: {e}")


def _build_dist_dfe_xml(
    tp_amb,
    c_cnpj_cpf,
    c_uf_autor,
    query_type,
    ult_nsu=None,
    nsu=None,
    ch_nfe=None,
):
    """
    Constrói o XML distDFeInt para o serviço NFeDistribuicaoDFe.

    query_type:
        'distNSU'  - distribui DFes a partir do ultNSU informado
        'consNSU'  - consulta DFe por NSU específico
        'consChNFe' - consulta NF-e por chave de acesso
    """
    ns = "http://www.portalfiscal.inf.br/nfe"
    root = etree.Element("{%s}distDFeInt" % ns, versao="1.01", nsmap={None: ns})

    tp_amb_el = etree.SubElement(root, "{%s}tpAmb" % ns)
    tp_amb_el.text = tp_amb

    c_uf_el = etree.SubElement(root, "{%s}cUFAutor" % ns)
    c_uf_el.text = str(c_uf_autor)

    # CNPJ ou CPF do interessado
    if len(c_cnpj_cpf) == 14:
        doc_el = etree.SubElement(root, "{%s}CNPJ" % ns)
    else:
        doc_el = etree.SubElement(root, "{%s}CPF" % ns)
    doc_el.text = c_cnpj_cpf

    if not query_type:
        raise UserError(_("consult_dist_dfe: Tipo de consulta não informado"))

    if query_type == "distNSU":
        if ult_nsu == None:
            raise UserError(_("consult_dist_dfe: Último NSU não informado"))
        dist_nsu_el = etree.SubElement(root, "{%s}distNSU" % ns)
        ult_nsu_el = etree.SubElement(dist_nsu_el, "{%s}ultNSU" % ns)
        ult_nsu_el.text = str(ult_nsu).zfill(15)

    elif query_type == "consNSU":
        if not nsu:
            raise UserError(_("NSU é obrigatório para consulta por NSU."))
        cons_nsu_el = etree.SubElement(root, "{%s}consNSU" % ns)
        nsu_el = etree.SubElement(cons_nsu_el, "{%s}NSU" % ns)
        nsu_el.text = str(nsu).zfill(15)

    elif query_type == "consChNFe":
        if not ch_nfe:
            raise UserError(_("Chave de acesso é obrigatória para consulta por chave."))
        cons_ch_el = etree.SubElement(root, "{%s}consChNFe" % ns)
        ch_el = etree.SubElement(cons_ch_el, "{%s}chNFe" % ns)
        ch_el.text = ch_nfe

    xml_string = etree.tostring(
        root, encoding="unicode", pretty_print=False, xml_declaration=False
    )

    validate_dfe_xml(root)

    return xml_string


def consult_dist_dfe(company, last_nsu=None):
    if not company:
        raise UserError(_("consult_dist_dfe: Empresa não encontrada"))

    certificate = company.get_nfe_certificate_pkcs12()
    if not certificate:
        raise UserError(
            _(
                "Nenhum certificado digital válido encontrado para a empresa.\n"
                "Configure um certificado A1 válido antes de realizar consultas."
            )
        )

    # Determinar ambiente
    tp_amb = "1" if company.fiscal_document_emission_env == "1" else "2"
    env_key = "production" if tp_amb == "1" else "homologation"
    url = NFE_DIST_DFE_URLS[env_key]

    state_ibge_code = company.state_id.ibge_code
    if not state_ibge_code:
        raise UserError(_("consult_dist_dfe: Código IBGE do estado não encontrado"))

    c_uf_autor = state_ibge_code

    company_vat = "".join(ch for ch in (company.vat or "") if ch.isdigit())
    if not company_vat or not cnpj_cpf.validar(company_vat):
        raise UserError(_("consult_dist_dfe: CNPJ/CPF da empresa inválido"))

    ult_nsu = 0
    if last_nsu:
        ult_nsu = last_nsu

    xml_content = _build_dist_dfe_xml(
        tp_amb=tp_amb,
        c_cnpj_cpf=company_vat,
        c_uf_autor=c_uf_autor,
        query_type="distNSU",
        ult_nsu=ult_nsu,
    )

    _logger.info(
        f"Consultando NFeDistribuicaoDFe - empresa={company.name} tipo=distNSU ultNSU={ult_nsu}"
    )
    _logger.debug(f"XML consulta:\n{xml_content}")

    response = _send_soap_request(url, xml_content, certificate)

    _logger.debug(f"Resposta SEFAZ:\n{response.text[:3000]}")

    result = _parse_dist_dfe_response(response.text)

    return result
