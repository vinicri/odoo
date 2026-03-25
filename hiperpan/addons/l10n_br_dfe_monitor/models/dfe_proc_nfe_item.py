"""
Brazilian DFe Monitor - Itens da NF-e Processada (det/prod)
"""

import logging
from odoo import api, fields, models

_logger = logging.getLogger(__name__)

NS = "http://www.portalfiscal.inf.br/nfe"


def _find(root, tag):
    el = root.find(f"{{{NS}}}{tag}")
    if el is not None:
        return el
    return root.find(f".//{{{NS}}}{tag}")


def _text(root, tag):
    el = _find(root, tag)
    return el.text if el is not None else None


def _fval(root, tag):
    v = _text(root, tag)
    if not v:
        return 0.0
    v = v.strip()
    v = v.replace(",", ".") if ("," in v and "." not in v) else v
    try:
        return float(v)
    except (ValueError, TypeError):
        return 0.0


class DfeProcNfeItem(models.Model):
    _name = "l10n_br_dfe_monitor.proc_nfe_item"
    _description = "Item da NF-e Processada (det/prod)"
    _order = "proc_nfe_id, n_item"
    _rec_name = "x_prod"

    proc_nfe_id = fields.Many2one(
        "l10n_br_dfe_monitor.proc_nfe",
        string="NF-e",
        required=True,
        ondelete="cascade",
        index=True,
    )

    n_item = fields.Integer(string="Nº Item", required=True, readonly=True)
    c_prod = fields.Char(
        string="Código Produto/Serviço", size=60, required=True, readonly=True
    )
    c_ean = fields.Char(string="GTIN", size=14, readonly=True)
    x_prod = fields.Char(string="Descrição", size=120, required=True, readonly=True)
    ncm = fields.Char(string="NCM", size=8, readonly=True, required=True)
    nve = fields.Char(string="NVE", size=6, readonly=True)
    cest = fields.Char(string="CEST", size=7, readonly=True)
    ind_escala = fields.Char(string="Ind. Escala Relevante", size=1, readonly=True)
    cnpj_fab = fields.Char(string="CNPJ Fabricante", size=14, readonly=True)
    c_benef = fields.Char(string="Cód. Benefício Fiscal", size=10, readonly=True)
    ex_tipi = fields.Char(string="EX TIPI", size=3, readonly=True)
    cfop = fields.Char(string="CFOP", size=4, required=True, readonly=True)
    u_com = fields.Char(
        string="Unidade Comercial", size=6, required=True, readonly=True
    )
    q_com = fields.Float(
        string="Qtd. Comercial", digits=(15, 4), required=True, readonly=True
    )
    v_un_com = fields.Float(
        string="Vlr. Unit. Comercial", digits=(21, 10), required=True, readonly=True
    )
    v_prod = fields.Float(
        string="Vlr. Total Bruto", digits=(13, 2), required=True, readonly=True
    )
    c_ean_trib = fields.Char(string="GTIN Tributável", size=14, readonly=True)
    u_trib = fields.Char(
        string="Unidade Tributável", size=6, required=True, readonly=True
    )
    q_trib = fields.Float(
        string="Qtd. Tributável", digits=(15, 4), required=True, readonly=True
    )
    v_un_trib = fields.Float(
        string="Vlr. Unit. Tributação", digits=(21, 10), required=True, readonly=True
    )
    v_frete = fields.Float(string="Frete", digits=(13, 2), readonly=True)
    v_seg = fields.Float(string="Seguro", digits=(13, 2), readonly=True)
    v_desc = fields.Float(string="Desconto", digits=(13, 2), readonly=True)
    v_outro = fields.Float(string="Outras Despesas", digits=(13, 2), readonly=True)
    ind_tot = fields.Selection(
        [("0", "Não compõe total"), ("1", "Compõe total")],
        string="Compõe Total NF-e",
        required=True,
        readonly=True,
    )

    @api.model
    def _create_from_det(self, proc_nfe, det_el):
        """
        Cria um item a partir do elemento <det nItem="N"> do XML.
        Retorna o registro criado ou None se prod não for encontrado.
        """
        n_item = det_el.get("nItem")
        prod = det_el.find(f"{{{NS}}}prod")
        if prod is None:
            raise ValueError(
                f"procNFe id={proc_nfe.id}: <prod> não encontrado no item nItem={n_item}"
            )

        vals = {
            "proc_nfe_id": proc_nfe.id,
            "n_item": int(n_item) if n_item else 0,
            # I02-I04
            "c_prod": _text(prod, "cProd"),
            "c_ean": _text(prod, "cEAN"),
            "x_prod": _text(prod, "xProd"),
            # I05, I05a
            "ncm": _text(prod, "NCM"),
            "nve": _text(prod, "NVE"),
            # I05b: CEST/indEscala/CNPJFab ficam diretamente em prod no XML real
            "cest": _text(prod, "CEST"),
            "ind_escala": _text(prod, "indEscala"),
            "cnpj_fab": _text(prod, "CNPJFab"),
            # I05f, I06
            "c_benef": _text(prod, "cBenef"),
            "ex_tipi": _text(prod, "EXTIPI"),
            # I08-I11
            "cfop": _text(prod, "CFOP"),
            "u_com": _text(prod, "uCom"),
            "q_com": _fval(prod, "qCom"),
            "v_un_com": _fval(prod, "vUnCom"),
            "v_prod": _fval(prod, "vProd"),
            # I12-I14a
            "c_ean_trib": _text(prod, "cEANTrib"),
            "u_trib": _text(prod, "uTrib"),
            "q_trib": _fval(prod, "qTrib"),
            "v_un_trib": _fval(prod, "vUnTrib"),
            # I15-I17b
            "v_frete": _fval(prod, "vFrete"),
            "v_seg": _fval(prod, "vSeg"),
            "v_desc": _fval(prod, "vDesc"),
            "v_outro": _fval(prod, "vOutro"),
            "ind_tot": _text(prod, "indTot"),
        }

        return self.create(vals)
