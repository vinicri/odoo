"""
Brazilian DFe Monitor - Itens da NF-e Processada (det/prod)
"""

import logging
from odoo import api, fields, models

_logger = logging.getLogger(__name__)

NS = "http://www.portalfiscal.inf.br/nfe"

# Tags de grupo ICMS → nome do elemento filho que contém os campos
# (CST régime normal: ICMS00..ICMS90; CSOSN Simples: ICMSSN101..ICMSSN900)
_ICMS_GROUPS = [
    "ICMS00",
    "ICMS10",
    "ICMS20",
    "ICMS30",
    "ICMS40",
    "ICMS51",
    "ICMS60",
    "ICMS70",
    "ICMS90",
    "ICMSSN101",
    "ICMSSN102",
    "ICMSSN201",
    "ICMSSN202",
    "ICMSSN500",
    "ICMSSN900",
]


def _find_direct(parent, tag):
    """Busca filho direto com namespace."""
    return parent.find(f"{{{NS}}}{tag}")


def _text(root, tag):
    el = root.find(f"{{{NS}}}{tag}")
    if el is None:
        el = root.find(f".//{{{NS}}}{tag}")
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


def _parse_icms(imposto_el):
    """
    Extrai os campos de ICMS do elemento <imposto>.
    Funciona para qualquer grupo ICMS/ICMSSN independente do CST/CSOSN.
    Retorna um dict com os campos populados (0.0 / None quando ausentes).
    """
    result = {}

    if imposto_el is None:
        return result

    icms_el = _find_direct(imposto_el, "ICMS")
    if icms_el is None:
        return result

    # Localizar o grupo interno (ICMS00, ICMSSN101, etc.)
    group = None
    for tag in _ICMS_GROUPS:
        group = _find_direct(icms_el, tag)
        if group is not None:
            break

    if group is None:
        return result

    def ft(tag):
        return _text(group, tag)

    def fv(tag):
        return _fval(group, tag)

    result["icms_orig"] = ft("orig")
    result["icms_cst_csosn"] = ft("CST") or ft("CSOSN")

    result["icms_mod_bc"] = ft("modBC")
    result["icms_v_bc"] = fv("vBC")
    result["icms_p_red_bc"] = fv("pRedBC")
    result["icms_p_icms"] = fv("pICMS")
    result["icms_v_icms"] = fv("vICMS")

    result["icms_p_fcp"] = fv("pFCP")
    result["icms_v_fcp"] = fv("vFCP")
    result["icms_v_bc_fcp"] = fv("vBCFCP")

    result["icms_p_cred_sn"] = fv("pCredSN")
    result["icms_v_cred_icms_sn"] = fv("vCredICMSSN")

    result["icms_mod_bc_st"] = ft("modBCST")
    result["icms_p_mva_st"] = fv("pMVAST")
    result["icms_p_red_bc_st"] = fv("pRedBCST")
    result["icms_v_bc_st"] = fv("vBCST")
    result["icms_p_icms_st"] = fv("pICMSST")
    result["icms_v_icms_st"] = fv("vICMSST")

    result["icms_v_bc_fcp_st"] = fv("vBCFCPST")
    result["icms_p_fcp_st"] = fv("pFCPST")
    result["icms_v_fcp_st"] = fv("vFCPST")

    result["icms_v_bc_st_ret"] = fv("vBCSTRet")
    result["icms_p_st"] = fv("pST")
    result["icms_v_icms_substituto"] = fv("vICMSSubstituto")
    result["icms_v_icms_st_ret"] = fv("vICMSSTRet")
    result["icms_v_bc_fcp_st_ret"] = fv("vBCFCPSTRet")
    result["icms_p_fcp_st_ret"] = fv("pFCPSTRet")
    result["icms_v_fcp_st_ret"] = fv("vFCPSTRet")

    result["icms_p_red_bc_efet"] = fv("pRedBCEfet")
    result["icms_v_bc_efet"] = fv("vBCEfet")
    result["icms_p_icms_efet"] = fv("pICMSEfet")
    result["icms_v_icms_efet"] = fv("vICMSEfet")

    result["icms_v_icms_deson"] = fv("vICMSDeson")
    result["icms_mot_des_icms"] = ft("motDesICMS")

    result["icms_p_dif"] = fv("pDif")
    result["icms_v_icms_dif"] = fv("vICMSDif")
    result["icms_v_icms_op"] = fv("vICMSOp")

    return result


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

    # ── prod ─────────────────────────────────────────────────────────────
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

    # ── ICMS – identificação ──────────────────────────────────────────────
    # N10 – Origem da mercadoria (0=Nacional, 1=Estrangeira-Imp. Direta, etc.)
    icms_orig = fields.Char(string="Origem Mercadoria", size=1, readonly=True)
    # N11 – Tributação do ICMS
    icms_cst_csosn = fields.Char(string="CST/CSOSN", size=3, readonly=True)

    # ── ICMS próprio ─────────────────────────────────────────────────────
    # N13 – Modalidade de determinação da BC do ICMS (0=MV Aj,1=Pauta,2=Preço Tab,3=Val Op)
    icms_mod_bc = fields.Char(string="Mod. Det. BC ICMS", size=1, readonly=True)
    # N15 – Valor da BC do ICMS (13v2)
    icms_v_bc = fields.Float(string="BC ICMS", digits=(13, 2), readonly=True)
    # N14 – Percentual de redução da BC (3v2-4)
    icms_p_red_bc = fields.Float(string="% Red. BC", digits=(3, 4), readonly=True)
    # N16 – Alíquota do imposto (3v2-4)
    icms_p_icms = fields.Float(string="Alíq. ICMS", digits=(3, 4), readonly=True)
    # N17 – Valor do ICMS (13v2)
    icms_v_icms = fields.Float(string="Vlr. ICMS", digits=(13, 2), readonly=True)

    # ── FCP próprio ───────────────────────────────────────────────────────
    # N17b – Valor da BC do FCP (13v2)
    icms_v_bc_fcp = fields.Float(string="BC FCP", digits=(13, 2), readonly=True)
    # N17c – Percentual do FCP (3v2-4)
    icms_p_fcp = fields.Float(string="% FCP", digits=(3, 4), readonly=True)
    # N17d – Valor do FCP (13v2)
    icms_v_fcp = fields.Float(string="Vlr. FCP", digits=(13, 2), readonly=True)

    # ── Simples Nacional crédito ──────────────────────────────────────────
    # N35 – Alíquota aplicável de cálculo do crédito (Simples Nacional) (3v2-4)
    icms_p_cred_sn = fields.Float(string="% Créd. SN", digits=(3, 4), readonly=True)
    # N36 – Valor crédito do ICMS que pode ser aproveitado (Simples Nacional) (13v2)
    icms_v_cred_icms_sn = fields.Float(
        string="Vlr. Créd. ICMS SN", digits=(13, 2), readonly=True
    )

    # ── ICMS ST ───────────────────────────────────────────────────────────
    # N18 – Modalidade de determinação da BC do ICMS ST (0=Preço Tab,1=Lista Neg,2=MV Aj,3=Dupla Pub,4=Margem Val Ag,5=Pauta)
    icms_mod_bc_st = fields.Char(string="Mod. Det. BC ST", size=1, readonly=True)
    # N19 – Percentual da MVA do ICMS ST (3v2-4)
    icms_p_mva_st = fields.Float(string="% MVA ST", digits=(3, 4), readonly=True)
    # N20 – Percentual de redução da BC do ICMS ST (3v2-4)
    icms_p_red_bc_st = fields.Float(string="% Red. BC ST", digits=(3, 4), readonly=True)
    # N21 – Valor da BC do ICMS ST (13v2)
    icms_v_bc_st = fields.Float(string="BC ICMS ST", digits=(13, 2), readonly=True)
    # N22 – Alíquota do ICMS ST (3v2-4)
    icms_p_icms_st = fields.Float(string="Alíq. ICMS ST", digits=(3, 4), readonly=True)
    # N23 – Valor do ICMS ST (13v2)
    icms_v_icms_st = fields.Float(string="Vlr. ICMS ST", digits=(13, 2), readonly=True)

    # ── FCP ST ────────────────────────────────────────────────────────────
    # N23a – Valor da BC do FCP retido por ST (13v2)
    icms_v_bc_fcp_st = fields.Float(string="BC FCP ST", digits=(13, 2), readonly=True)
    # N23b – Percentual do FCP retido por ST (3v2-4)
    icms_p_fcp_st = fields.Float(string="% FCP ST", digits=(3, 4), readonly=True)
    # N23c – Valor do FCP retido por ST (13v2)
    icms_v_fcp_st = fields.Float(string="Vlr. FCP ST", digits=(13, 2), readonly=True)

    # ── ST Retido ─────────────────────────────────────────────────────────
    # N24 – Valor da BC do ICMS ST retido anteriormente (13v2)
    icms_v_bc_st_ret = fields.Float(
        string="BC ST Retido", digits=(13, 2), readonly=True
    )
    # N24a – Alíquota suportada pelo consumidor final (3v2-4)
    icms_p_st = fields.Float(
        string="Alíq. ST Cons. Final", digits=(3, 4), readonly=True
    )
    # N24b – Valor do ICMS próprio do substituto (13v2)
    icms_v_icms_substituto = fields.Float(
        string="Vlr. ICMS Substituto", digits=(13, 2), readonly=True
    )
    # N25 – Valor do ICMS ST retido anteriormente (13v2)
    icms_v_icms_st_ret = fields.Float(
        string="Vlr. ICMS ST Retido", digits=(13, 2), readonly=True
    )
    # N25a – Valor da BC do FCP ST retido anteriormente (13v2)
    icms_v_bc_fcp_st_ret = fields.Float(
        string="BC FCP ST Retido", digits=(13, 2), readonly=True
    )
    # N25b – Percentual do FCP ST retido anteriormente (3v2-4)
    icms_p_fcp_st_ret = fields.Float(
        string="% FCP ST Retido", digits=(3, 4), readonly=True
    )
    # N25c – Valor do FCP ST retido anteriormente (13v2)
    icms_v_fcp_st_ret = fields.Float(
        string="Vlr. FCP ST Retido", digits=(13, 2), readonly=True
    )

    # ── ICMS Efetivo (CST 60/CSOSN 500) ──────────────────────────────────
    # N26 – Percentual de redução da BC efetiva (3v2-4)
    icms_p_red_bc_efet = fields.Float(
        string="% Red. BC Efet.", digits=(5, 4), readonly=True
    )
    # N27 – Valor da BC efetiva (13v2)
    icms_v_bc_efet = fields.Float(string="BC Efetiva", digits=(13, 2), readonly=True)
    # N28 – Alíquota do ICMS efetiva (3v2-4)
    icms_p_icms_efet = fields.Float(
        string="Alíq. ICMS Efet.", digits=(5, 4), readonly=True
    )
    # N29 – Valor do ICMS efetivo (13v2)
    icms_v_icms_efet = fields.Float(
        string="Vlr. ICMS Efet.", digits=(13, 2), readonly=True
    )

    # ── Desoneração ───────────────────────────────────────────────────────
    # N28a – Valor do ICMS desonerado (13v2)
    icms_v_icms_deson = fields.Float(
        string="Vlr. ICMS Desonerado", digits=(13, 2), readonly=True
    )
    # N28b – Motivo da desoneração do ICMS (1=Táxi,3=Produtor Ag,…,12=Outros)
    icms_mot_des_icms = fields.Char(string="Motivo Desoneração", size=2, readonly=True)

    # ── Diferimento (CST 51) ──────────────────────────────────────────────
    # N37 – Percentual do diferimento (3v2-4)
    icms_p_dif = fields.Float(string="% Diferimento", digits=(3, 4), readonly=True)
    # N38 – Valor do ICMS diferido (13v2)
    icms_v_icms_dif = fields.Float(
        string="Vlr. ICMS Diferido", digits=(13, 2), readonly=True
    )
    # N39 – Valor do ICMS da operação (13v2)
    icms_v_icms_op = fields.Float(
        string="Vlr. ICMS Operação", digits=(13, 2), readonly=True
    )

    @api.model
    def _create_from_det(self, proc_nfe, det_el):
        """
        Cria um item a partir do elemento <det nItem="N"> do XML.
        Retorna o registro criado ou None se prod não for encontrado.
        """
        n_item = det_el.get("nItem")
        prod = _find_direct(det_el, "prod")
        if prod is None:
            raise ValueError(
                f"procNFe id={proc_nfe.id}: <prod> não encontrado no item nItem={n_item}"
            )

        imposto = _find_direct(det_el, "imposto")

        vals = {
            "proc_nfe_id": proc_nfe.id,
            "n_item": int(n_item) if n_item else 0,
            # prod
            "c_prod": _text(prod, "cProd"),
            "c_ean": _text(prod, "cEAN"),
            "x_prod": _text(prod, "xProd"),
            "ncm": _text(prod, "NCM"),
            "nve": _text(prod, "NVE"),
            "cest": _text(prod, "CEST"),
            "ind_escala": _text(prod, "indEscala"),
            "cnpj_fab": _text(prod, "CNPJFab"),
            "c_benef": _text(prod, "cBenef"),
            "ex_tipi": _text(prod, "EXTIPI"),
            "cfop": _text(prod, "CFOP"),
            "u_com": _text(prod, "uCom"),
            "q_com": _fval(prod, "qCom"),
            "v_un_com": _fval(prod, "vUnCom"),
            "v_prod": _fval(prod, "vProd"),
            "c_ean_trib": _text(prod, "cEANTrib"),
            "u_trib": _text(prod, "uTrib"),
            "q_trib": _fval(prod, "qTrib"),
            "v_un_trib": _fval(prod, "vUnTrib"),
            "v_frete": _fval(prod, "vFrete"),
            "v_seg": _fval(prod, "vSeg"),
            "v_desc": _fval(prod, "vDesc"),
            "v_outro": _fval(prod, "vOutro"),
            "ind_tot": _text(prod, "indTot"),
        }

        vals.update(_parse_icms(imposto))

        return self.create(vals)
