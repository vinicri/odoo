"""
Envio de Manifestação do Destinatário para o Ambiente Nacional (SEFAZ).

Implementa o serviço NFeRecepcaoEvento conforme leiaute confRecebto_v1.00.
"""

import logging
import os
import tempfile
import base64
import requests
from datetime import datetime, timezone
from lxml import etree
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    PrivateFormat,
    NoEncryption,
    pkcs12,
)
from erpbrasil.assinatura.assinatura import Assinatura
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)

NS = "http://www.portalfiscal.inf.br/nfe"
SCHEMA_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "schemas",
    "manifestacao",
)


def _load_manifestacao_schema(schema_filename):
    schema_path = os.path.join(SCHEMA_DIR, schema_filename)
    with open(schema_path, "rb") as f:
        doc = etree.parse(f)
    return etree.XMLSchema(doc)


def _validate_env_evento(env_element):
    """Valida o <envEvento> contra envConfRecebto_v1.00.xsd."""
    try:
        schema = _load_manifestacao_schema("envConfRecebto_v1.00.xsd")
        if not schema.validate(env_element):
            errors = "\n".join(f"Linha {e.line}: {e.message}" for e in schema.error_log)
            _logger.error("Validação XSD envEvento falhou:\n%s", errors)
            raise ValidationError(f"XML de manifestação inválido:\n{errors}")
    except (ValidationError, UserError):
        raise
    except Exception as e:
        _logger.warning("Não foi possível validar contra XSD: %s", e)


# Ambiente Nacional — único endpoint para manifestação (cOrgao=91)
RECEPCAO_EVENTO_URLS = {
    "1": "https://nfe.fazenda.mg.gov.br/nfe2/services/NFeRecepcaoEvento4",
    "2": "https://hom.nfe.fazenda.gov.br/NFeRecepcaoEvento4/NFeRecepcaoEvento4.asmx",
}

# tpEvento → descEvento exato conforme XSD
DESC_EVENTO = {
    "210200": "Confirmacao da Operacao",
    "210210": "Ciencia da Operacao",
    "210220": "Desconhecimento da Operacao",
    "210240": "Operacao nao Realizada",
}


def _now_br():
    """Retorna datetime atual no formato exigido pelo schema: AAAA-MM-DDThh:mm:ss-03:00"""
    now = datetime.now(timezone.utc).astimezone()
    return now.strftime("%Y-%m-%dT%H:%M:%S") + "-03:00"


def _build_evento_xml(
    tp_amb, cnpj, ch_nfe, tp_evento, n_seq_evento=1, x_just=None, c_orgao="91"
):
    """
    Constrói o elemento <evento> com <infEvento> e <detEvento> para manifestação.
    Retorna (xml_element, event_id) — xml_element ainda não assinado.
    """
    ver_evento = "1.00"
    n_seq = str(n_seq_evento)
    # Id = "ID" + tpEvento(6) + chNFe(44) + nSeqEvento(2 com zeros)
    event_id = f"ID{tp_evento}{ch_nfe}{n_seq.zfill(2)}"

    evento = etree.Element(f"{{{NS}}}evento", versao="1.00", nsmap={None: NS})
    inf = etree.SubElement(evento, f"{{{NS}}}infEvento", Id=event_id)

    etree.SubElement(inf, f"{{{NS}}}cOrgao").text = c_orgao
    etree.SubElement(inf, f"{{{NS}}}tpAmb").text = tp_amb
    etree.SubElement(inf, f"{{{NS}}}CNPJ").text = cnpj
    etree.SubElement(inf, f"{{{NS}}}chNFe").text = ch_nfe
    etree.SubElement(inf, f"{{{NS}}}dhEvento").text = _now_br()
    etree.SubElement(inf, f"{{{NS}}}tpEvento").text = tp_evento
    etree.SubElement(inf, f"{{{NS}}}nSeqEvento").text = n_seq
    etree.SubElement(inf, f"{{{NS}}}verEvento").text = ver_evento

    det = etree.SubElement(inf, f"{{{NS}}}detEvento", versao=ver_evento)
    etree.SubElement(det, f"{{{NS}}}descEvento").text = DESC_EVENTO[tp_evento]
    if x_just and tp_evento == "210240":
        etree.SubElement(det, f"{{{NS}}}xJust").text = x_just

    return evento, event_id


def _build_env_evento_xml(
    tp_amb,
    cnpj,
    ch_nfe,
    tp_evento,
    n_seq_evento=1,
    x_just=None,
    certificate=None,
    c_orgao="91",
):
    """
    Constrói o <envEvento> completo, assina o <evento> e retorna o XML como string.
    """
    import time

    id_lote = str(int(time.time()))[-15:]

    evento, event_id = _build_evento_xml(
        tp_amb, cnpj, ch_nfe, tp_evento, n_seq_evento, x_just, c_orgao=c_orgao
    )

    # Assinar o elemento <evento> com referência ao Id do infEvento
    assinador = Assinatura(certificate)
    signed_tree = assinador.assina_xml2(evento, event_id)

    if isinstance(signed_tree, (str, bytes)):
        signed_tree = etree.fromstring(
            signed_tree.encode("utf-8") if isinstance(signed_tree, str) else signed_tree
        )

    # Limpar quebras de linha nos campos base64 (SEFAZ rejeita)
    ds_ns = {"ds": "http://www.w3.org/2000/09/xmldsig#"}
    for tag in ("ds:SignatureValue", "ds:DigestValue", "ds:X509Certificate"):
        for elem in signed_tree.findall(f".//{tag}", ds_ns):
            if elem.text:
                elem.text = (
                    elem.text.replace("\n", "").replace("\r", "").replace(" ", "")
                )

    env = etree.Element(f"{{{NS}}}envEvento", versao="1.00", nsmap={None: NS})
    etree.SubElement(env, f"{{{NS}}}idLote").text = id_lote
    env.append(signed_tree)

    _validate_env_evento(env)

    # Re-serializa garantindo namespace default para o NS nfe (sem prefixo ns0:)
    # O lxml usa prefixo quando o elemento vem de fromstring sem nsmap declarado
    xml_str = etree.tostring(env, encoding="unicode", xml_declaration=False)

    # Substitui prefixos gerados automaticamente pelo lxml (ns0:, nfe:) pelo namespace default
    # mas preserva ds: (xmldsig) que é obrigatório com prefixo
    import re

    # Remove declarações de namespace com prefixo para o NS da NF-e
    xml_str = re.sub(
        r'\s+xmlns:(?!ds\b)\w+="http://www\.portalfiscal\.inf\.br/nfe[^"]*"',
        "",
        xml_str,
    )
    # Remove declarações xmlns: que são ns0/nfe duplicatas do namespace default já declarado
    xml_str = re.sub(r'\s+xmlns:(?!ds\b)\w+="[^"]*"', "", xml_str)
    # Substitui tags com prefixo nfe:  ou ns0: por tags sem prefixo (apenas NS nfe)
    xml_str = re.sub(r"<(/?)(nfe|ns\d+):([\w])", r"<\1\3", xml_str)

    return xml_str


def _send_soap_manifestacao(url, xml_content, certificate_pkcs12):
    """
    Envia requisição SOAP NFeRecepcaoEvento4 e retorna o texto da resposta.
    """
    cert_bytes = base64.b64decode(certificate_pkcs12["cert_file"])
    private_key, certificate, _ = pkcs12.load_key_and_certificates(
        cert_bytes, certificate_pkcs12["password"].encode("utf-8")
    )
    key_pem = private_key.private_bytes(
        encoding=Encoding.PEM,
        format=PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=NoEncryption(),
    )
    cert_pem = certificate.public_bytes(Encoding.PEM)

    cert_path = key_path = None
    try:
        with tempfile.NamedTemporaryFile(mode="wb", delete=False, suffix=".pem") as cf:
            cf.write(cert_pem)
            cert_path = cf.name
        with tempfile.NamedTemporaryFile(mode="wb", delete=False, suffix=".key") as kf:
            kf.write(key_pem)
            key_path = kf.name

        soap_env = f"""<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope xmlns:soap="http://www.w3.org/2003/05/soap-envelope"
               xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
               xmlns:xsd="http://www.w3.org/2001/XMLSchema">
  <soap:Body>
    <nfeDadosMsg xmlns="http://www.portalfiscal.inf.br/nfe/wsdl/NFeRecepcaoEvento4">
{xml_content}
    </nfeDadosMsg>
  </soap:Body>
</soap:Envelope>"""

        _logger.debug("SOAP manifestação para %s:\n%s", url, soap_env[:3000])

        headers = {
            "Content-Type": "application/soap+xml; charset=utf-8",
            "SOAPAction": "http://www.portalfiscal.inf.br/nfe/wsdl/NFeRecepcaoEvento4",
        }
        response = requests.post(
            url,
            data=soap_env.encode("utf-8"),
            headers=headers,
            cert=(cert_path, key_path),
            timeout=60,
        )

        if response.status_code != 200:
            raise UserError(
                f"Erro HTTP ao enviar manifestação: {response.status_code} {response.text}"
            )

        return response.text

    finally:
        for path in (cert_path, key_path):
            if path:
                try:
                    os.unlink(path)
                except Exception:
                    pass


def _parse_recepcao_evento_response(response_text):
    """
    Faz parse do retorno SOAP do NFeRecepcaoEvento4.
    Retorna dict com c_stat, x_motivo, n_prot.
    Lança UserError se a SEFAZ retornou erro.
    """
    try:
        root = etree.fromstring(response_text.encode("utf-8"))
        ns = {
            "soap": "http://www.w3.org/2003/05/soap-envelope",
            "nfe": NS,
        }

        ret_events = root.xpath("//nfe:retEvento/nfe:infEvento", namespaces=ns)
        if not ret_events:
            # Tentar retEnvEvento direto
            ret_events = root.xpath(
                "//nfe:retEnvEvento/nfe:retEvento/nfe:infEvento", namespaces=ns
            )

        if not ret_events:
            _logger.error(
                "Resposta NFeRecepcaoEvento4 inesperada:\n%s", response_text[:2000]
            )
            raise UserError("Resposta inválida da SEFAZ: retEvento não encontrado")

        inf = ret_events[0]

        def ft(tag):
            el = inf.find(f"nfe:{tag}", ns)
            return el.text if el is not None else None

        c_stat = ft("cStat")
        x_motivo = ft("xMotivo")
        n_prot = ft("nProt")

        _logger.info(
            "NFeRecepcaoEvento4 — cStat=%s xMotivo=%s nProt=%s",
            c_stat,
            x_motivo,
            n_prot,
        )

        # 135 = Evento registrado e vinculado a NF-e
        # 573 = Duplicidade de evento (já manifestado)
        if c_stat not in ("135", "573"):
            raise UserError(f"SEFAZ recusou a manifestação: {c_stat} — {x_motivo}")

        return {"c_stat": c_stat, "x_motivo": x_motivo, "n_prot": n_prot}

    except UserError:
        raise
    except Exception as e:
        _logger.error(
            "Erro ao fazer parse da resposta NFeRecepcaoEvento4: %s", e, exc_info=True
        )
        raise UserError(f"Erro ao processar resposta da SEFAZ: {e}")


def send_manifestacao(company, ch_nfe, tp_evento, tp_amb, x_just=None, n_seq_evento=1):
    """
    Envia manifestação do destinatário para o Ambiente Nacional.

    Args:
        company: res.company com certificado NF-e configurado
        ch_nfe: Chave de acesso da NF-e (44 chars)
        tp_evento: "210200" | "210210" | "210220" | "210240"
        tp_amb: "1" (Produção) | "2" (Homologação)
        x_just: Justificativa (obrigatória para 210240)
        n_seq_evento: Sequencial do evento (padrão 1)

    Returns:
        dict com c_stat, x_motivo, n_prot
    """
    if tp_evento not in DESC_EVENTO:
        raise UserError(f"Tipo de evento de manifestação inválido: {tp_evento}")

    if tp_evento == "210240" and not x_just:
        raise UserError("Justificativa é obrigatória para Operação não Realizada.")

    company_vat = "".join(c for c in (company.vat or "") if c.isdigit())
    if not company_vat:
        raise UserError("CNPJ da empresa não configurado.")

    certificate = company.get_nfe_certificate()
    certificate_pkcs12 = company.get_nfe_certificate_pkcs12()

    c_orgao = str(company.state_id.ibge_code) if company.state_id.ibge_code else "91"

    url = RECEPCAO_EVENTO_URLS.get(tp_amb, RECEPCAO_EVENTO_URLS["2"])

    xml_content = _build_env_evento_xml(
        tp_amb=tp_amb,
        cnpj=company_vat,
        ch_nfe=ch_nfe,
        tp_evento=tp_evento,
        n_seq_evento=n_seq_evento,
        x_just=x_just,
        certificate=certificate,
        c_orgao=c_orgao,
    )

    _logger.info(
        "Enviando manifestação tpEvento=%s chNFe=%s empresa=%s",
        tp_evento,
        ch_nfe,
        company.name,
    )
    _logger.info(f"XML manifestação:\n{xml_content}")

    response_text = _send_soap_manifestacao(url, xml_content, certificate_pkcs12)
    _logger.info(f"Resposta SEFAZ:\n{response_text[:3000]}")
    return _parse_recepcao_evento_response(response_text)
