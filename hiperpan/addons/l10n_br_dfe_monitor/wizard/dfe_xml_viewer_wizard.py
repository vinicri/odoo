"""
Brazilian DFe Monitor - Wizard para visualizar conteúdo XML
"""

import base64
import logging
from lxml import etree
from odoo import fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class DfeXmlViewerWizard(models.TransientModel):
    _name = "l10n_br_dfe_monitor.xml_viewer_wizard"
    _description = "Visualizador de XML DFe"

    xml_content = fields.Text(string="Conteúdo XML", readonly=True)

    def _format_xml(self, xml_bytes):
        try:
            root = etree.fromstring(xml_bytes)
            return etree.tostring(root, pretty_print=True, encoding="unicode")
        except etree.XMLSyntaxError:
            return xml_bytes.decode("utf-8", errors="replace")

    def action_open_xml_viewer(self, document_id):
        doc = self.env["l10n_br_dfe_monitor.document"].browse(document_id)
        if not doc.xml_file:
            raise UserError(_("Este documento não possui arquivo XML."))

        raw = base64.b64decode(doc.xml_file)
        formatted = self._format_xml(raw)

        wizard = self.create({"xml_content": formatted})
        return {
            "type": "ir.actions.act_window",
            "name": _("XML — NSU %s") % doc.nsu,
            "res_model": self._name,
            "res_id": wizard.id,
            "view_mode": "form",
            "target": "new",
        }
