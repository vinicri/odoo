"""
Wizard para upload manual de XML de DFe
"""

import base64
import logging

from lxml import etree
from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

NS = "http://www.portalfiscal.inf.br/nfe"

# Mapeamento tag-raiz → schema (prefixo)
_ROOT_SCHEMA_MAP = {
    "nfeProc": "procNFe",
    "NFe": "procNFe",
    "resNFe": "resNFe",
    "resEvento": "resEvento",
    "procEventoNFe": "procEventoNFe",
}


def _detect_schema(root):
    tag = etree.QName(root.tag).localname
    return _ROOT_SCHEMA_MAP.get(tag)


def _extract_nsu_from_xml(root):
    """Tenta extrair NSU do atributo ou conteúdo do XML. Retorna None se não encontrar."""
    for tag in ("NSU", "nsu"):
        el = root.find(f".//{{{NS}}}{tag}")
        if el is not None and el.text:
            try:
                return int(el.text.strip())
            except ValueError:
                pass
    return None


def _extract_tp_amb(root):
    el = root.find(f".//{{{NS}}}tpAmb")
    return el.text.strip() if el is not None and el.text else "1"


class DfeUploadWizard(models.TransientModel):
    _name = "l10n_br_dfe_monitor.upload.wizard"
    _description = "Upload Manual de XML DFe"

    xml_file = fields.Binary(string="Arquivo XML", required=True)
    xml_filename = fields.Char(string="Nome do Arquivo")

    def action_upload(self):
        self.ensure_one()

        if not self.xml_file:
            raise UserError(_("Selecione um arquivo XML para importar."))

        raw = base64.b64decode(self.xml_file)

        try:
            root = etree.fromstring(raw)
        except etree.XMLSyntaxError as e:
            raise UserError(_("Arquivo XML inválido: %s") % str(e))

        schema = _detect_schema(root)
        if not schema:
            tag = etree.QName(root.tag).localname
            raise UserError(
                _("Tag raiz '%s' não reconhecida. Schemas suportados: procNFe, resNFe, resEvento, procEventoNFe.") % tag
            )

        # Versão do schema
        versao = root.get("versao") or ""
        schema_full = f"{schema}_v{versao}" if versao else schema

        tp_amb = _extract_tp_amb(root)
        nsu = _extract_nsu_from_xml(root)

        # Se não encontrou NSU no XML, gera um negativo sequencial para não colidir
        DfeDoc = self.env["l10n_br_dfe_monitor.document"]
        if nsu is None:
            min_nsu = DfeDoc.search(
                [("company_id", "=", self.env.company.id), ("nsu", "<", 0)],
                order="nsu asc",
                limit=1,
            )
            nsu = (min_nsu.nsu - 1) if min_nsu else -1

        filename = self.xml_filename or f"{schema}_{nsu}.xml"

        # Verificar duplicata
        existing = DfeDoc.search([
            ("company_id", "=", self.env.company.id),
            ("nsu", "=", nsu),
            ("tp_amb", "=", tp_amb),
        ], limit=1)
        if existing:
            raise UserError(
                _("Já existe um documento com NSU=%s e ambiente=%s (id=%s).") % (nsu, tp_amb, existing.id)
            )

        doc = DfeDoc.create({
            "company_id": self.env.company.id,
            "nsu": nsu,
            "schema": schema_full,
            "tp_amb": tp_amb,
            "xml_file": self.xml_file,
            "xml_filename": filename,
            "state": "pending",
        })

        _logger.info("DFe importado manualmente: id=%s schema=%s NSU=%s", doc.id, schema_full, nsu)

        return {
            "type": "ir.actions.act_window",
            "name": _("Documento Importado"),
            "res_model": "l10n_br_dfe_monitor.document",
            "res_id": doc.id,
            "view_mode": "form",
            "target": "current",
        }
