"""
Wizard para baixar, em um único ZIP, os XMLs das NF-e processadas.

Aberto como ação em massa a partir da lista de NF-e Processadas: recebe as
NF-e selecionadas e permite refinar por período (data de emissão), emitente e
ambiente antes de gerar o ZIP.

Cada XML no ZIP recebe o nome:
    {timestamp_unix_da_dh_emi}-{YYYYMMDD_da_dh_emi}-{razao_social_emissor}.xml
"""

import base64
import io
import re
import zipfile

from odoo import fields, models, _
from odoo.exceptions import UserError


class DfeDownloadXmlWizard(models.TransientModel):
    _name = "l10n_br_dfe_monitor.download_xml_wizard"
    _description = "Baixar XMLs (ZIP)"

    proc_nfe_ids = fields.Many2many(
        "l10n_br_dfe_monitor.proc_nfe",
        relation="dfe_download_xml_wizard_proc_nfe_rel",
        column1="wizard_id",
        column2="proc_nfe_id",
        string="NF-e Selecionadas",
    )
    date_from = fields.Date(string="Data de Emissão (de)")
    date_to = fields.Date(string="Data de Emissão (até)")
    emit_cnpj = fields.Char(string="CNPJ do Emitente")
    tp_amb = fields.Selection(
        [("1", "Produção"), ("2", "Homologação")],
        string="Ambiente",
    )

    # Resultado: o arquivo ZIP gerado (baixado pela própria action).
    zip_file = fields.Binary(string="Arquivo ZIP", readonly=True, attachment=False)
    zip_filename = fields.Char(string="Nome do ZIP", readonly=True)

    def _filtered_proc_nfe(self):
        """Aplica os filtros do wizard sobre as NF-e selecionadas."""
        self.ensure_one()
        records = self.proc_nfe_ids
        if self.date_from:
            records = records.filtered(
                lambda r: r.dh_emi and r.dh_emi.date() >= self.date_from
            )
        if self.date_to:
            records = records.filtered(
                lambda r: r.dh_emi and r.dh_emi.date() <= self.date_to
            )
        if self.emit_cnpj:
            cnpj = re.sub(r"\D", "", self.emit_cnpj)
            records = records.filtered(
                lambda r: (r.emit_cnpj or "") == cnpj
            )
        if self.tp_amb:
            records = records.filtered(lambda r: r.tp_amb == self.tp_amb)
        return records

    @staticmethod
    def _sanitize_filename(value):
        """Remove caracteres inválidos para nome de arquivo, preservando acentos."""
        value = (value or "").strip()
        # remove separadores de caminho e caracteres proibidos no zip/OS
        value = re.sub(r'[\\/:*?"<>|\r\n\t]+', " ", value)
        value = re.sub(r"\s+", " ", value).strip()
        return value or "SEM-RAZAO-SOCIAL"

    def _xml_name_for(self, record):
        """Monta o nome do XML: unix(dh_emi)-YYYYMMDD(dh_emi)-razaosocial.xml"""
        dh_emi = record.dh_emi
        unix_ts = int(dh_emi.timestamp()) if dh_emi else 0
        date_str = dh_emi.strftime("%Y%m%d") if dh_emi else "00000000"
        razao = self._sanitize_filename(record.emit_x_nome)
        return f"{unix_ts}-{date_str}-{razao}.xml"

    def action_download_zip(self):
        self.ensure_one()
        records = self._filtered_proc_nfe()
        if not records:
            raise UserError(
                _("Nenhuma NF-e atende aos filtros informados.")
            )

        buffer = io.BytesIO()
        used_names = {}
        added = 0
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            for record in records:
                document = record.dfe_document_id
                if not document or not document.xml_file:
                    continue
                xml_bytes = base64.b64decode(document.xml_file)

                name = self._xml_name_for(record)
                # evita colisões de nome dentro do ZIP
                if name in used_names:
                    used_names[name] += 1
                    root, ext = name.rsplit(".", 1)
                    name = f"{root}-{used_names[name]}.{ext}"
                else:
                    used_names[name] = 0
                zf.writestr(name, xml_bytes)
                added += 1

        if not added:
            raise UserError(
                _("As NF-e selecionadas não possuem arquivo XML disponível.")
            )

        self.zip_file = base64.b64encode(buffer.getvalue())
        self.zip_filename = "nfe_xmls_%s.zip" % fields.Datetime.now().strftime(
            "%Y%m%d_%H%M%S"
        )
        return {
            "type": "ir.actions.act_url",
            "url": (
                "/web/content/%s/%s/zip_file/%s?download=true"
                % (self._name, self.id, self.zip_filename)
            ),
            "target": "self",
        }
