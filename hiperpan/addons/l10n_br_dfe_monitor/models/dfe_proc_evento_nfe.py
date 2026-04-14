"""
Brazilian DFe Monitor - Evento de NF-e (procEventoNFe)
"""

import base64
import logging
from datetime import datetime, timezone
from lxml import etree
from odoo import api, fields, models, _
from .common import InvalidTipoEventoError

_logger = logging.getLogger(__name__)

NS = "http://www.portalfiscal.inf.br/nfe"
NS_MAP = {"nfe": NS}

TP_EVENTO_SELECTION = [
    ("110110", "Carta de Correção Eletrônica"),
    ("110111", "Cancelamento pelo Emitente"),
    ("110112", "Cancelamento por Substituição"),
    ("110140", "EPEC – Emissão em Contingência"),
    ("110150", "Ator Interessado – Transportador"),
    ("111500", "Pedido de Prorrogação 1º Prazo"),
    ("111501", "Pedido de Prorrogação 2º Prazo"),
    ("111502", "Cancelamento de Prorrogação 1º Prazo"),
    ("111503", "Cancelamento de Prorrogação 2º Prazo"),
    ("210200", "Confirmação de Operação pelo Destinatário"),
    ("210210", "Ciência da Operação pelo Destinatário"),
    ("210220", "Desconhecimento da Operação pelo Destinatário"),
    ("210240", "Operação não Realizada"),
    ("400100", "Alerta Fisco: Simulação Operação Emitente"),
    ("400101", "Cancelamento Evento Fisco 400100"),
    ("400104", "Alerta Fisco: Simulação Operação Emitente Inex."),
    ("400105", "Cancelamento Evento Fisco 400104"),
    ("400120", "Alerta Fisco: Mercadoria Sem Origem Comprovada"),
    ("400121", "Cancelamento Evento Fisco 400120"),
    ("400200", "Documento Fiscal Inidôneo"),
    ("400201", "Cancelamento Evento Fisco 400200"),
    ("400300", "Visto Eletrônico do Fisco"),
    ("400301", "Cancelamento Evento Fisco 400300"),
    ("411500", "Fisco: Resposta Prorrogação 1º Prazo"),
    ("411501", "Fisco: Resposta Prorrogação 2º Prazo"),
    ("411502", "Fisco: Resp. Cancelamento Prorrogação 1º Prazo"),
    ("411503", "Fisco: Resp. Cancelamento Prorrogação 2º Prazo"),
    ("500100", "Alerta Fisco: Simulação Operação Destinatário"),
    ("500101", "Cancelamento Evento Fisco 500100"),
    ("500104", "Alerta Fisco: Simulação Operação Destinatário Inex"),
    ("500105", "Cancelamento Evento Fisco 500104"),
    ("610500", "Registro Passagem NF-e"),
    ("610501", "Cancelamento Registro Passagem NF-e"),
]

# Mapeamento tpEvento → valor manifestacao em res_nfe
MANIFESTACAO_MAP = {
    "210200": "confirmado",
    "210210": "ciencia",
    "210220": "desconhecido",
    "210240": "nao_realizada",
}


def _ft(el, tag):
    """Encontra texto de uma tag filha (com ou sem namespace)."""
    if el is None:
        return None
    child = el.find(f"nfe:{tag}", NS_MAP)
    if child is None:
        child = el.find(f"{{{NS}}}{tag}")
    return child.text if child is not None else None


def _find(el, tag):
    """Encontra elemento filho (com ou sem namespace)."""
    if el is None:
        return None
    child = el.find(f"nfe:{tag}", NS_MAP)
    if child is None:
        child = el.find(f"{{{NS}}}{tag}")
    return child


def _parse_dh(s):
    """Parse ISO-8601 com offset para UTC naive."""
    if not s:
        return None
    s = s.strip().replace("Z", "+00:00")
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def _parse_det_cancelamento(det_el):
    return {
        "det_n_prot": _ft(det_el, "nProt"),
        "det_x_just": _ft(det_el, "xJust"),
        "det_ch_nfe_ref": _ft(det_el, "chNFeRef"),
        "det_c_orgao_autor": _ft(det_el, "cOrgaoAutor"),
    }


def _parse_det_carta_correcao(det_el):
    return {
        "det_x_correcao": _ft(det_el, "xCorrecao"),
        "det_x_cond_uso": _ft(det_el, "xCondUso"),
    }


def _parse_det_manifestacao(det_el):
    return {
        "det_x_just": _ft(det_el, "xJust"),
    }


class DfeProcEventoNfe(models.Model):
    _name = "l10n_br_dfe_monitor.proc_evento_nfe"
    _description = "Evento de NF-e (procEventoNFe)"
    _order = "dh_evento desc, id desc"
    _rec_name = "tp_evento"

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
    res_nfe_id = fields.Many2one(
        "l10n_br_dfe_monitor.res_nfe",
        string="Resumo NF-e",
        ondelete="set null",
        index=True,
        readonly=True,
    )

    proc_nfe_id = fields.Many2one(
        "l10n_br_dfe_monitor.proc_nfe",
        string="NF-e Completa",
        ondelete="set null",
        index=True,
        readonly=True,
    )

    # Campos genéricos — infEvento (entrada)
    tp_amb = fields.Selection(
        [("1", "Produção"), ("2", "Homologação")],
        string="Ambiente",
        required=True,
        readonly=True,
    )
    autor_cnpj = fields.Char(string="CNPJ Autor", size=14, readonly=True)
    autor_cpf = fields.Char(string="CPF Autor", size=11, readonly=True)
    ch_nfe = fields.Char(
        string="Chave de Acesso", size=44, index=True, readonly=True, required=True
    )
    dh_evento = fields.Datetime(string="Data/Hora Evento", readonly=True, required=True)
    tp_evento = fields.Selection(
        TP_EVENTO_SELECTION,
        string="Tipo de Evento",
        required=True,
        readonly=True,
        index=True,
    )
    n_seq_evento = fields.Char(string="Seq. Evento", size=2, readonly=True)
    ver_evento = fields.Char(string="Versão Evento", size=4, readonly=True)

    # Campos detEvento — comuns a vários tipos
    det_desc_evento = fields.Char(string="Descrição do Evento", size=60, readonly=True)
    det_c_orgao_autor = fields.Char(
        string="Cód. Órgão Autor",
        size=2,
        readonly=True,
        help="Exclusivo Cancelamento por substituição (110112)",
    )
    det_tp_autor = fields.Char(
        string="Tipo Autor",
        size=1,
        readonly=True,
        help="Exclusivo Cancelamento por substituição (110112)",
    )
    det_ver_aplic = fields.Char(
        string="Versão Aplicativo Autor",
        size=20,
        readonly=True,
        help="Exclusivo Cancelamento por substituição (110112)",
    )
    det_n_prot = fields.Char(
        string="Protocolo NF-e (det)",
        size=15,
        readonly=True,
        help="Cancelamento: protocolo da NF-e a cancelar",
    )
    det_x_just = fields.Char(
        string="Justificativa",
        size=255,
        readonly=True,
        help="Cancelamento / Operação não Realizada",
    )
    det_ch_nfe_ref = fields.Char(
        string="Chave NF-e Substituta",
        size=44,
        readonly=True,
        help="Exclusivo Cancelamento por substituição (110112)",
    )
    det_x_correcao = fields.Char(
        string="Texto Correção",
        size=1000,
        readonly=True,
        help="Carta de Correção (110110)",
    )
    det_x_cond_uso = fields.Text(
        string="Condições de Uso CC-e", readonly=True, help="Carta de Correção (110110)"
    )

    # Campos retEvento — infEvento (saída)
    c_stat = fields.Char(string="Código Status", size=3, readonly=True)
    x_motivo = fields.Char(string="Motivo", size=255, readonly=True)
    x_evento = fields.Char(string="Resultado", size=60, readonly=True)
    n_prot = fields.Char(string="Protocolo Evento", size=15, readonly=True)
    cnpj_dest = fields.Char(
        string="CNPJ Destinatário",
        size=14,
        readonly=True,
        help="Específico para cancelamento (110111)",
    )
    cpf_dest = fields.Char(
        string="CPF Destinatário",
        size=11,
        readonly=True,
        help="Específico para cancelamento (110111)",
    )
    ch_nfe_pend = fields.Char(
        string="Chaves EPEC Pendentes",
        readonly=True,
        help="Específico para EPEC (110140) — múltiplas chaves separadas por vírgula",
    )

    @api.model
    def create_from_dfe_document(self, dfe_doc):
        """
        Cria um registro procEventoNFe a partir de um DfeDocument com schema procEventoNFe.
        Retorna o registro criado ou None em caso de erro.
        """
        try:
            raw_xml = base64.b64decode(dfe_doc.xml_file)
            root = etree.fromstring(raw_xml)

            # infEvento da mensagem de entrada
            inf_evento_in = _find(_find(root, "evento"), "infEvento")
            # infEvento do retorno
            inf_evento_ret = _find(_find(root, "retEvento"), "infEvento")

            tp_evento = _ft(inf_evento_in, "tpEvento")
            ch_nfe = _ft(inf_evento_in, "chNFe")

            det_el = _find(inf_evento_in, "detEvento")

            all_tp_evento = ["110111", "110112", "110110"] + list(
                MANIFESTACAO_MAP.keys()
            )
            if tp_evento not in all_tp_evento:
                raise InvalidTipoEventoError(tp_evento)

            # Parse detEvento por tipo
            det_vals = {}
            if det_el is not None:
                det_vals["det_desc_evento"] = _ft(det_el, "descEvento")
                if tp_evento in ("110111", "110112"):
                    det_vals.update(_parse_det_cancelamento(det_el))
                elif tp_evento == "110110":
                    det_vals.update(_parse_det_carta_correcao(det_el))
                elif tp_evento in MANIFESTACAO_MAP:
                    det_vals.update(_parse_det_manifestacao(det_el))
                else:
                    # Tipos genéricos: tenta extrair campos comuns se presentes
                    det_vals["det_n_prot"] = _ft(det_el, "nProt")
                    det_vals["det_x_just"] = _ft(det_el, "xJust")

            # Chaves EPEC pendentes (0-50 ocorrências)
            ch_nfe_pend_list = []
            if inf_evento_ret is not None:
                for el in inf_evento_ret.findall(f"nfe:chNFePend", NS_MAP):
                    if el.text:
                        ch_nfe_pend_list.append(el.text)

            vals = {
                "company_id": dfe_doc.company_id.id,
                "dfe_document_id": dfe_doc.id,
                "tp_amb": dfe_doc.tp_amb,
                "autor_cnpj": _ft(inf_evento_in, "CNPJ"),
                "autor_cpf": _ft(inf_evento_in, "CPF"),
                "ch_nfe": ch_nfe,
                "dh_evento": _parse_dh(_ft(inf_evento_in, "dhEvento")),
                "tp_evento": tp_evento,
                "n_seq_evento": _ft(inf_evento_in, "nSeqEvento"),
                "ver_evento": _ft(inf_evento_in, "verEvento"),
                # retEvento
                "c_stat": _ft(inf_evento_ret, "cStat"),
                "x_motivo": _ft(inf_evento_ret, "xMotivo"),
                "x_evento": _ft(inf_evento_ret, "xEvento"),
                "n_prot": _ft(inf_evento_ret, "nProt"),
                "cnpj_dest": _ft(inf_evento_ret, "CNPJDest"),
                "cpf_dest": _ft(inf_evento_ret, "CPFDest"),
                "ch_nfe_pend": (
                    ",".join(ch_nfe_pend_list) if ch_nfe_pend_list else False
                ),
            }
            vals.update(det_vals)

            record = self.create(vals)
            _logger.info(
                f"procEventoNFe criado: id={record.id} tpEvento={tp_evento} chNFe={ch_nfe} NSU={dfe_doc.nsu}"
            )

            # Vincula res_nfe pelo ch_nfe
            if ch_nfe:
                res_nfe = self.env["l10n_br_dfe_monitor.res_nfe"].search(
                    [
                        ("ch_nfe", "=", ch_nfe),
                        ("company_id", "=", dfe_doc.company_id.id),
                        ("tp_amb", "=", dfe_doc.tp_amb),
                    ],
                    limit=1,
                )
                if res_nfe:
                    record.res_nfe_id = res_nfe.id
                    # Atualiza manifestação do res_nfe se for evento de manifestação
                    # manifest_val = MANIFESTACAO_MAP.get(tp_evento)
                    # if manifest_val:
                    #     res_nfe.manifestacao = manifest_val

                proc_nfe = self.env["l10n_br_dfe_monitor.proc_nfe"].search(
                    [
                        ("ch_nfe", "=", ch_nfe),
                        ("company_id", "=", dfe_doc.company_id.id),
                        ("tp_amb", "=", dfe_doc.tp_amb),
                    ],
                    limit=1,
                )
                if proc_nfe:
                    record.proc_nfe_id = proc_nfe.id

            return record

        except Exception as e:
            _logger.error(
                f"Erro ao criar procEventoNFe para DFe NSU={dfe_doc.nsu}: {e}",
                exc_info=True,
            )
            raise
