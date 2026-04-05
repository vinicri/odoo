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
from ..utils import schema_validator, consult_dist_dfe as consult_dist_dfe_utils


_logger = logging.getLogger(__name__)

# URL do Ambiente Nacional para NFeDistribuicaoDFe
NFE_DIST_DFE_URLS = {
    "production": "https://www1.nfe.fazenda.gov.br/NFeDistribuicaoDFe/NFeDistribuicaoDFe.asmx",
    "homologation": "https://hom1.nfe.fazenda.gov.br/NFeDistribuicaoDFe/NFeDistribuicaoDFe.asmx",
}


SCHEMA_TYPE_RES_NFE = "resNFe"
SCHEMA_TYPE_PROC_NFE = "procNFe"
SCHEMA_TYPE_RES_EVENTO = "resEvento"
SCHEMA_TYPE_PROC_EVENTO_NFE = "procEventoNFe"
SCHEMA_TYPES = [
    (SCHEMA_TYPE_RES_NFE, "Resumo NF-e"),
    (SCHEMA_TYPE_PROC_NFE, "NF-e Completa"),
    (SCHEMA_TYPE_RES_EVENTO, "Resumo de Evento"),
    (SCHEMA_TYPE_PROC_EVENTO_NFE, "Evento NF-e"),
]


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

    nsu = fields.Integer(string="NSU", required=True, index=True)

    schema = fields.Char(string="Schema XML", readonly=True, required=True)

    document_type = fields.Selection(
        string="Tipo de Documento",
        selection=SCHEMA_TYPES,
        compute="_compute_document_type",
        store=True,
    )

    tp_amb = fields.Selection(
        string="Tipo de Ambiente",
        selection=[("1", "Produção"), ("2", "Homologação")],
        required=True,
    )

    # xml_content = fields.Text(string="Conteúdo XML")
    xml_file = fields.Binary(string="Arquivo XML", required=True)
    xml_filename = fields.Char(string="Nome do Arquivo XML", required=True)

    # ch_nfe = fields.Char(string="Chave de Acesso", index=True)
    # dh_recbto = fields.Char(string="Data/Hora Recebimento")

    # emit_cnpj = fields.Char(string="CNPJ Emitente")
    # emit_name = fields.Char(string="Nome Emitente")

    # dest_cnpj = fields.Char(string="CNPJ/CPF Destinatário")
    # dest_name = fields.Char(string="Nome Destinatário")

    # n_nf = fields.Char(string="Número NF-e")
    # v_nf = fields.Char(string="Valor Total")

    # dh_emi = fields.Char(string="Data Emissão")

    state = fields.Selection(
        [
            ("pending", "Pendente"),
            ("processed", "Processado"),
            ("error", "Erro"),
        ],
        string="Status",
        default="pending",
        required=True,
    )
    # notes = fields.Text(string="Observações")

    _sql_constraints = [
        (
            "unique_company_nsu",
            "UNIQUE(company_id, nsu, tp_amb)",
            "Já existe um documento com este NSU para esta empresa e tipo de ambiente.",
        )
    ]

    @api.depends("schema")
    def _compute_document_type(self):
        for rec in self:
            rec.document_type = False
            schema_key = (rec.schema or "").split("_", 1)[0]
            for schema_type in SCHEMA_TYPES:
                if schema_key == schema_type[0]:
                    rec.document_type = schema_type[0]
                    break

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

    def action_set_all_pending(self):
        self.search([("state", "!=", "pending")]).state = "pending"
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Processamento"),
                "message": _("Todos os documentos foram definidos como pendentes."),
            },
        }

    @api.model
    def _process_res_nfe(self):
        """Processa o registro de Resumo NF-e"""
        company = self.env.company
        tp_amb = company.fiscal_document_emission_env
        pending_res_nfe = self.env["l10n_br_dfe_monitor.document"].search(
            [
                ("company_id", "=", company.id),
                ("tp_amb", "=", tp_amb),
                ("state", "=", "pending"),
                ("document_type", "=", SCHEMA_TYPE_RES_NFE),
            ]
        )
        ResNfe = self.env["l10n_br_dfe_monitor.res_nfe"]
        for res_nfe in pending_res_nfe:
            record = ResNfe.create_from_dfe_document(res_nfe)
            if record:
                res_nfe.state = "processed"
            else:
                _logger.warning(
                    f"Erro ao criar res_nfe: {res_nfe.id} - {res_nfe.dfe_document_id.nsu}"
                )
                res_nfe.state = "error"

    def action_process_res_nfe(self):
        """Botão da lista: processa resumos NF-e pendentes para a empresa atual."""
        self._process_res_nfe()
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Processamento"),
                "message": _("Resumos NF-e pendentes foram processados."),
                "type": "success",
                "sticky": False,
            },
        }

    @api.model
    def _process_proc_nfe(self):
        """Processa documentos procNFe pendentes, extraindo dados para l10n_br_dfe_monitor.proc_nfe."""
        company = self.env.company
        tp_amb = company.fiscal_document_emission_env
        pending = self.env["l10n_br_dfe_monitor.document"].search(
            [
                ("company_id", "=", company.id),
                ("tp_amb", "=", tp_amb),
                ("state", "=", "pending"),
                ("document_type", "=", SCHEMA_TYPE_PROC_NFE),
            ]
        )
        ProcNfe = self.env["l10n_br_dfe_monitor.proc_nfe"]
        for dfe_doc in pending:
            try:
                record = ProcNfe._create_from_dfe_document(dfe_doc)
                if record:
                    dfe_doc.state = "processed"
                else:
                    _logger.warning(
                        f"Erro ao criar procNfe: {dfe_doc.id} - {dfe_doc.dfe_document_id.nsu}"
                    )
                    dfe_doc.state = "error"
            except Exception as e:
                _logger.error(
                    f"Erro ao processar procNFe NSU={dfe_doc.nsu}: {e}",
                    exc_info=True,
                )
                dfe_doc.state = "error"

    def action_process_proc_nfe(self):
        """Botão da lista: processa NF-e completas pendentes para a empresa atual."""
        self._process_proc_nfe()
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Processamento"),
                "message": _("NF-e completas pendentes foram processadas."),
                "type": "success",
                "sticky": False,
            },
        }

    def action_open_upload_wizard(self):
        return {
            "type": "ir.actions.act_window",
            "name": _("Importar XML DFe"),
            "res_model": "l10n_br_dfe_monitor.upload.wizard",
            "view_mode": "form",
            "target": "new",
        }

    @api.model
    def consult_dist_dfe(self):
        company = self.env.company
        tp_amb = company.fiscal_document_emission_env

        last_nsu = self.search(
            [("company_id", "=", company.id), ("tp_amb", "=", tp_amb)],
            order="nsu desc",
            limit=1,
        ).nsu

        result = False
        isLastNSUPage = False

        def save_documents(documents):
            for doc in documents:
                existing = self.search(
                    [
                        ("company_id", "=", company.id),
                        ("nsu", "=", doc["nsu"]),
                        ("tp_amb", "=", tp_amb),
                    ],
                    limit=1,
                )
                if existing:
                    continue

                xml_bytes = (
                    doc["xml"].encode("utf-8")
                    if isinstance(doc["xml"], str)
                    else doc["xml"]
                )
                xml_b64 = base64.b64encode(xml_bytes).decode()
                xml_filename = f"dfe_{doc['nsu']}.xml"

                vals = {
                    "company_id": company.id,
                    "nsu": int(doc.get("nsu")),
                    "schema": doc.get("schema"),
                    "xml_file": xml_b64,
                    "xml_filename": xml_filename,
                    "state": "pending",
                    "tp_amb": tp_amb,
                }

                self.create(vals)

        while not isLastNSUPage:
            try:
                result = consult_dist_dfe_utils.consult_dist_dfe(company, last_nsu)
                if (
                    result.get("ult_nsu") == result.get("max_nsu")
                    or result.get("c_stat") == "137"
                ):
                    if result.get("c_stat") == "137":
                        isLastNSUPage = True
                        continue

                    documents = result.get("documents")
                    if documents and len(documents) > 0:
                        save_documents(documents)
                    else:
                        _logger.warning(
                            f"Nenhum documento encontrado mesmo que o c_stat seja 138. Resultado: {result}"
                        )
                    isLastNSUPage = True
                else:
                    documents = result.get("documents")
                    if documents and len(documents) > 0:
                        save_documents(documents)
                    else:
                        _logger.warning(
                            f"Nenhum documento encontrado mesmo que o c_stat seja 138. Resultado: {result}"
                        )

                    last_nsu = int(result.get("ult_nsu"))

            except Exception as e:
                _logger.error(
                    f"Erro ao consultar NFeDistribuicaoDFe: {e}", exc_info=True
                )
                raise UserError(_("Erro ao consultar NFeDistribuicaoDFe: %s") % e)

    @api.model
    def consult_dist_dfe_old(
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
        c_uf_autor = state_code.ibge_code

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
