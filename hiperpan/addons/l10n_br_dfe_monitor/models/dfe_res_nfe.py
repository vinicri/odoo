"""
Brazilian DFe Monitor - Resumo de NF-e (resNFe)
"""

import logging
from lxml import etree
from odoo import api, fields, models, _
from datetime import datetime, timezone

_logger = logging.getLogger(__name__)

MANIFESTACAO_SELECTION = [
    ("ciencia", "Ciência da Operação"),
    ("confirmado", "Confirmação da Operação"),
    ("nao_realizada", "Operação Não Realizada"),
    ("desconhecido", "Desconhecimento da Operação"),
]

C_SIT_NFE_LABELS = {
    "1": "Uso Autorizado",
    "2": "Uso Denegado",
    "3": "NF-e Cancelada",
}

TP_NF_LABELS = {
    "0": "Entrada",
    "1": "Saída",
}


def _parse_nfe_dh(s):
    """Parse dhEmi/dhRecbto (ISO-8601 com offset, ex. -03:00 ou Z) para UTC naive (Odoo Datetime)."""
    if not s:
        return None
    s = s.strip().replace("Z", "+00:00")
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


class DfeResNfe(models.Model):
    _name = "l10n_br_dfe_monitor.res_nfe"
    _description = "Resumo de NF-e (resNFe)"
    _order = "dh_recbto desc, id desc"
    _rec_name = "ch_nfe"

    company_id = fields.Many2one(
        "res.company",
        string="Empresa",
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )

    dfe_document_id = fields.Many2one(
        "l10n_br_dfe_monitor.document",
        string="DFe Documento",
        ondelete="set null",
        index=True,
    )

    # Campos do schema resNFe_v1.01.xsd
    versao = fields.Char(string="Versão", readonly=True, required=True)
    ch_nfe = fields.Char(
        string="Chave de Acesso", size=44, index=True, readonly=True, required=True
    )
    emit_cnpj = fields.Char(string="CNPJ Emitente", size=14)
    emit_cpf = fields.Char(string="CPF Emitente", size=11)
    x_nome = fields.Char(
        string="Razão Social / Nome Emitente", readonly=True, required=True
    )
    ie = fields.Char(string="IE Emitente", readonly=True)
    dh_emi = fields.Datetime(string="Data de Emissão", readonly=True, required=True)
    tp_nf = fields.Selection(
        [("0", "Entrada"), ("1", "Saída")],
        string="Tipo de Operação",
        readonly=True,
        required=True,
    )
    v_nf = fields.Float(string="Valor Total da NF-e", readonly=True, required=True)
    dig_val = fields.Char(string="Digest Value", readonly=True, required=True)
    dh_recbto = fields.Datetime(
        string="Data de Autorização", readonly=True, required=True
    )
    n_prot = fields.Char(string="Número do Protocolo", readonly=True, required=True)
    c_sit_nfe = fields.Selection(
        [("1", "Uso Autorizado"), ("2", "Uso Denegado"), ("3", "NF-e Cancelada")],
        string="Situação da NF-e",
        required=True,
        readonly=True,
    )

    # Manifestação do destinatário
    manifestacao = fields.Selection(
        MANIFESTACAO_SELECTION,
        string="Manifestação do Destinatário",
    )

    tp_amb = fields.Selection(
        [("1", "Produção"), ("2", "Homologação")],
        string="Tipo de Ambiente",
        readonly=True,
        required=True,
    )

    @api.model
    def create_from_dfe_document(self, dfe_doc):
        """
        Cria um registro resNFe a partir de um DfeDocument com schema resNFe.
        Retorna o registro criado ou None em caso de erro.
        """
        try:
            xml_bytes = dfe_doc.xml_file
            if not xml_bytes:
                _logger.warning(f"DFe {dfe_doc.nsu}: xml_file vazio, ignorando.")
                return None

            import base64

            raw_xml = base64.b64decode(xml_bytes)
            root = etree.fromstring(raw_xml)

            ns = {"nfe": "http://www.portalfiscal.inf.br/nfe"}

            def find_text(tag):
                el = root.find(f"nfe:{tag}", ns)
                if el is None:
                    el = root.find(f".//{{{ns['nfe']}}}{tag}")
                return el.text if el is not None else None

            versao = root.get("versao")
            ch_nfe = find_text("chNFe")
            emit_cnpj = find_text("CNPJ")
            emit_cpf = find_text("CPF")
            x_nome = find_text("xNome")
            ie = find_text("IE")
            dh_emi = find_text("dhEmi")
            tp_nf = find_text("tpNF")
            v_nf = find_text("vNF")
            dig_val = find_text("digVal")
            dh_recbto = find_text("dhRecbto")
            n_prot = find_text("nProt")
            c_sit_nfe = find_text("cSitNFe")

            vals = {
                "company_id": dfe_doc.company_id.id,
                "dfe_document_id": dfe_doc.id,
                "tp_amb": dfe_doc.tp_amb,
                "versao": versao,
                "ch_nfe": ch_nfe,
                "emit_cnpj": emit_cnpj,
                "emit_cpf": emit_cpf,
                "x_nome": x_nome,
                "ie": ie,
                "dh_emi": _parse_nfe_dh(dh_emi),
                "tp_nf": tp_nf,
                "v_nf": v_nf,
                "dig_val": dig_val,
                "dh_recbto": _parse_nfe_dh(dh_recbto),
                "n_prot": n_prot,
                "c_sit_nfe": c_sit_nfe,
            }

            record = self.create(vals)
            _logger.info(
                f"resNFe criado: id={record.id} chNFe={ch_nfe} NSU={dfe_doc.nsu}"
            )
            return record

        except Exception as e:
            _logger.error(
                f"Erro ao criar resNFe para DFe NSU={dfe_doc.nsu}: {e}",
                exc_info=True,
            )
            return None
