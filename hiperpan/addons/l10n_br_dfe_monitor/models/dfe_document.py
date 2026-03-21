"""
Brazilian DFe Monitor - Documento Fiscal Eletrônico
"""

import base64
import gzip
import logging
import tempfile
import os
from lxml import etree
import requests
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    PrivateFormat,
    NoEncryption,
    pkcs12,
)
from odoo import api, fields, models, _
from odoo.exceptions import UserError
from ..utils import schema_validator

_logger = logging.getLogger(__name__)

# URL do Ambiente Nacional para NFeDistribuicaoDFe
NFE_DIST_DFE_URLS = {
    "production": "https://www1.nfe.fazenda.gov.br/NFeDistribuicaoDFe/NFeDistribuicaoDFe.asmx",
    "homologation": "https://hom1.nfe.fazenda.gov.br/NFeDistribuicaoDFe/NFeDistribuicaoDFe.asmx",
}

SCHEMA_TYPE_LABELS = {
    "resNFe": "Resumo NF-e",
    "procNFe": "NF-e Completa",
    "resEvento": "Resumo de Evento",
    "procEventoNFe": "Evento NF-e",
}


class DfeDocument(models.Model):
    _name = "l10n_br_dfe_monitor.document"
    _description = "Documento Fiscal Eletrônico (DFe)"
    _order = "nsu desc"
    _rec_name = "nsu"

    company_id = fields.Many2one(
        "res.company",
        string="Empresa",
        required=True,
        default=lambda self: self.env.company,
    )
    nsu = fields.Char(string="NSU", required=True, index=True)
    schema = fields.Char(string="Schema XML", readonly=True)
    document_type = fields.Char(
        string="Tipo de Documento", compute="_compute_document_type", store=True
    )
    xml_content = fields.Text(string="Conteúdo XML")
    xml_file = fields.Binary(string="Arquivo XML")
    xml_filename = fields.Char(string="Nome do Arquivo XML")
    ch_nfe = fields.Char(string="Chave de Acesso", index=True)
    dh_recbto = fields.Char(string="Data/Hora Recebimento")
    emit_cnpj = fields.Char(string="CNPJ Emitente")
    emit_name = fields.Char(string="Nome Emitente")
    dest_cnpj = fields.Char(string="CNPJ/CPF Destinatário")
    dest_name = fields.Char(string="Nome Destinatário")
    n_nf = fields.Char(string="Número NF-e")
    v_nf = fields.Char(string="Valor Total")
    dh_emi = fields.Char(string="Data Emissão")
    state = fields.Selection(
        [
            ("new", "Novo"),
            ("processed", "Processado"),
            ("error", "Erro"),
        ],
        string="Status",
        default="new",
        required=True,
    )
    notes = fields.Text(string="Observações")

    _sql_constraints = [
        (
            "unique_company_nsu",
            "UNIQUE(company_id, nsu)",
            "Já existe um documento com este NSU para esta empresa.",
        )
    ]

    @api.depends("schema")
    def _compute_document_type(self):
        for rec in self:
            doc_type = "Desconhecido"
            if rec.schema:
                for key, label in SCHEMA_TYPE_LABELS.items():
                    if key in rec.schema:
                        doc_type = label
                        break
            rec.document_type = doc_type

    def _extract_nfe_data(self, xml_string, schema):
        """Extrai dados relevantes do XML do DFe"""
        data = {}
        try:
            root = etree.fromstring(
                xml_string.encode("utf-8")
                if isinstance(xml_string, str)
                else xml_string
            )
            ns = {"nfe": "http://www.portalfiscal.inf.br/nfe"}

            if "resNFe" in schema:
                # Resumo NF-e
                ch_nfe = root.find(".//nfe:chNFe", ns) or root.find(
                    ".//{http://www.portalfiscal.inf.br/nfe}chNFe"
                )
                if ch_nfe is not None:
                    data["ch_nfe"] = ch_nfe.text

                emit_name = root.find(".//nfe:xNome", ns)
                if emit_name is not None:
                    data["emit_name"] = emit_name.text

                v_nf = root.find(".//nfe:vNF", ns)
                if v_nf is not None:
                    data["v_nf"] = v_nf.text

                dh_emi = root.find(".//nfe:dhEmi", ns)
                if dh_emi is not None:
                    data["dh_emi"] = dh_emi.text

                dh_recbto = root.find(".//nfe:dhRecbto", ns)
                if dh_recbto is not None:
                    data["dh_recbto"] = dh_recbto.text

                n_nf = root.find(".//nfe:nNF", ns)
                if n_nf is not None:
                    data["n_nf"] = n_nf.text

            elif "procNFe" in schema or "nfeProc" in schema:
                # NF-e completa
                ch_nfe = root.find(".//{http://www.portalfiscal.inf.br/nfe}chNFe")
                if ch_nfe is not None:
                    data["ch_nfe"] = ch_nfe.text

                emit_cnpj = root.find(
                    ".//{http://www.portalfiscal.inf.br/nfe}emit/{http://www.portalfiscal.inf.br/nfe}CNPJ"
                )
                if emit_cnpj is not None:
                    data["emit_cnpj"] = emit_cnpj.text

                emit_name = root.find(
                    ".//{http://www.portalfiscal.inf.br/nfe}emit/{http://www.portalfiscal.inf.br/nfe}xNome"
                )
                if emit_name is not None:
                    data["emit_name"] = emit_name.text

                dest_cnpj = root.find(
                    ".//{http://www.portalfiscal.inf.br/nfe}dest/{http://www.portalfiscal.inf.br/nfe}CNPJ"
                )
                dest_cpf = root.find(
                    ".//{http://www.portalfiscal.inf.br/nfe}dest/{http://www.portalfiscal.inf.br/nfe}CPF"
                )
                if dest_cnpj is not None:
                    data["dest_cnpj"] = dest_cnpj.text
                elif dest_cpf is not None:
                    data["dest_cnpj"] = dest_cpf.text

                dest_name = root.find(
                    ".//{http://www.portalfiscal.inf.br/nfe}dest/{http://www.portalfiscal.inf.br/nfe}xNome"
                )
                if dest_name is not None:
                    data["dest_name"] = dest_name.text

                v_nf = root.find(".//{http://www.portalfiscal.inf.br/nfe}vNF")
                if v_nf is not None:
                    data["v_nf"] = v_nf.text

                n_nf = root.find(".//{http://www.portalfiscal.inf.br/nfe}nNF")
                if n_nf is not None:
                    data["n_nf"] = n_nf.text

                dh_emi = root.find(".//{http://www.portalfiscal.inf.br/nfe}dhEmi")
                if dh_emi is not None:
                    data["dh_emi"] = dh_emi.text

        except Exception as e:
            _logger.warning(f"Erro ao extrair dados do XML (schema={schema}): {e}")

        return data

    @api.model
    def _send_soap_request(self, url, xml_content, certificado):
        """
        Envia requisição SOAP para o Ambiente Nacional NFeDistribuicaoDFe
        """
        try:
            cert_bytes = base64.b64decode(certificado["cert_file"])
            private_key, certificate, _ = pkcs12.load_key_and_certificates(
                cert_bytes, certificado["password"].encode("utf-8")
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
                _logger.error(
                    f"Erro HTTP: {response.status_code} - {response.text[:500]}"
                )
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

    @api.model
    def _build_dist_dfe_xml(
        self,
        company_doc,
        ult_nsu,
        tp_amb,
        c_uf_autor,
        query_type="distNSU",
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
        tp_amb_el.text = tp_amb  # "1"=produção / "2"=homologação

        c_uf_el = etree.SubElement(root, "{%s}cUFAutor" % ns)
        c_uf_el.text = str(c_uf_autor)

        # CNPJ ou CPF do interessado
        if len(company_doc) == 14:
            doc_el = etree.SubElement(root, "{%s}CNPJ" % ns)
        else:
            doc_el = etree.SubElement(root, "{%s}CPF" % ns)
        doc_el.text = company_doc

        if query_type == "distNSU":
            dist_nsu_el = etree.SubElement(root, "{%s}distNSU" % ns)
            ult_nsu_el = etree.SubElement(dist_nsu_el, "{%s}ultNSU" % ns)
            ult_nsu_el.text = str(1).zfill(15)

        elif query_type == "consNSU":
            if not nsu:
                raise UserError(_("NSU é obrigatório para consulta por NSU."))
            cons_nsu_el = etree.SubElement(root, "{%s}consNSU" % ns)
            nsu_el = etree.SubElement(cons_nsu_el, "{%s}NSU" % ns)
            nsu_el.text = str(nsu).zfill(15)

        elif query_type == "consChNFe":
            if not ch_nfe:
                raise UserError(
                    _("Chave de acesso é obrigatória para consulta por chave.")
                )
            cons_ch_el = etree.SubElement(root, "{%s}consChNFe" % ns)
            ch_el = etree.SubElement(cons_ch_el, "{%s}chNFe" % ns)
            ch_el.text = ch_nfe

        xml_string = etree.tostring(
            root, encoding="unicode", pretty_print=False, xml_declaration=False
        )

        schema_validator.validate_dfe_xml(root)

        return xml_string

    @api.model
    def _parse_dist_dfe_response(self, response_text):
        """
        Faz o parse da resposta do NFeDistribuicaoDFe.
        Retorna dict com: c_stat, x_motivo, ult_nsu, max_nsu, documents[]
        """
        try:
            root = etree.fromstring(response_text.encode("utf-8"))

            namespaces = {
                "soap": "http://www.w3.org/2003/05/soap-envelope",
                "wsdl": "http://www.portalfiscal.inf.br/nfe/wsdl/NFeDistribuicaoDFe",
                "nfe": "http://www.portalfiscal.inf.br/nfe",
            }

            # Localizar retDistDFeInt
            ret = root.xpath("//nfe:retDistDFeInt", namespaces=namespaces)
            if not ret:
                ret = root.xpath("//*[local-name()='retDistDFeInt']")

            if not ret:
                _logger.error("Elemento retDistDFeInt não encontrado na resposta")
                _logger.debug(f"Resposta XML:\n{response_text[:2000]}")
                raise UserError(
                    _("Resposta inválida da SEFAZ: retDistDFeInt não encontrado")
                )

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
                        _logger.warning(
                            f"Erro ao descompactar docZip NSU={nsu_attr}: {e}"
                        )
                        xml_str = compressed  # fallback: guardar comprimido

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

    @api.model
    def _get_uf_ibge_code(self, state_code):
        """Retorna o código IBGE numérico da UF"""
        UF_IBGE = {
            "AC": "12",
            "AL": "27",
            "AP": "16",
            "AM": "13",
            "BA": "29",
            "CE": "23",
            "DF": "53",
            "ES": "32",
            "GO": "52",
            "MA": "21",
            "MT": "51",
            "MS": "50",
            "MG": "31",
            "PA": "15",
            "PB": "25",
            "PR": "41",
            "PE": "26",
            "PI": "22",
            "RJ": "33",
            "RN": "24",
            "RS": "43",
            "RO": "11",
            "RR": "14",
            "SC": "42",
            "SP": "35",
            "SE": "28",
            "TO": "17",
        }
        return UF_IBGE.get(state_code.upper(), "35")

    @api.model
    def consult_dist_dfe(
        self, company=None, query_type="distNSU", nsu=None, ch_nfe=None
    ):
        """
        Realiza a consulta ao serviço NFeDistribuicaoDFe e armazena os documentos.

        Args:
            company: res.company (default: empresa atual)
            query_type: 'distNSU', 'consNSU' ou 'consChNFe'
            nsu: NSU específico (para consNSU)
            ch_nfe: Chave de acesso (para consChNFe)

        Returns:
            dict com resultado da consulta
        """
        if not company:
            company = self.env.company

        # Obter certificado
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

        # Código IBGE da UF da empresa
        state_code = company.state_id.code
        if not state_code:
            raise UserError(_("Informe o estado da empresa no cadastro da empresa."))
        c_uf_autor = self._get_uf_ibge_code(state_code)

        # CNPJ da empresa (apenas números)
        company_vat = "".join(ch for ch in (company.vat or "") if ch.isdigit())
        if not company_vat:
            raise UserError(_("Informe o CNPJ/CPF da empresa no cadastro da empresa."))

        # Último NSU armazenado para distNSU
        ult_nsu = 0
        if query_type == "distNSU":
            last_doc = self.search(
                [("company_id", "=", company.id)],
                order="nsu desc",
                limit=1,
            )
            if last_doc:
                try:
                    ult_nsu = int(last_doc.nsu)
                except ValueError:
                    ult_nsu = 0

        # Construir XML
        xml_content = self._build_dist_dfe_xml(
            company_doc=company_vat,
            ult_nsu=ult_nsu,
            tp_amb=tp_amb,
            c_uf_autor=c_uf_autor,
            query_type=query_type,
            nsu=nsu,
            ch_nfe=ch_nfe,
        )

        _logger.info(
            f"Consultando NFeDistribuicaoDFe - empresa={company.name} tipo={query_type} ultNSU={ult_nsu}"
        )
        _logger.debug(f"XML consulta:\n{xml_content}")

        response = self._send_soap_request(url, xml_content, certificate)
        _logger.debug(f"Resposta SEFAZ:\n{response.text[:3000]}")

        result = self._parse_dist_dfe_response(response.text)

        # Armazenar documentos recebidos
        new_docs = []
        for doc in result.get("documents", []):
            existing = self.search(
                [
                    ("company_id", "=", company.id),
                    ("nsu", "=", doc["nsu"]),
                ],
                limit=1,
            )
            if existing:
                continue

            nfe_data = self._extract_nfe_data(doc["xml"], doc.get("schema", ""))

            xml_bytes = (
                doc["xml"].encode("utf-8")
                if isinstance(doc["xml"], str)
                else doc["xml"]
            )
            xml_b64 = base64.b64encode(xml_bytes).decode()
            xml_filename = f"dfe_{doc['nsu']}.xml"

            vals = {
                "company_id": company.id,
                "nsu": doc["nsu"],
                "schema": doc.get("schema", ""),
                "xml_content": doc["xml"],
                "xml_file": xml_b64,
                "xml_filename": xml_filename,
                "state": "new",
            }
            vals.update(nfe_data)

            new_doc = self.create(vals)
            new_docs.append(new_doc.id)

        result["new_count"] = len(new_docs)
        result["new_doc_ids"] = new_docs

        return result
