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


def _parse_ipi(imposto_el):
    """
    Extrai os campos de IPI do elemento <imposto>.
    Suporta os grupos IPITrib (CST 00,49,50,99) e IPINT (CST 01-05,51-55).
    Retorna um dict com os campos populados (0.0 / None quando ausentes).
    """
    result = {}

    if imposto_el is None:
        return result

    ipi_el = _find_direct(imposto_el, "IPI")
    if ipi_el is None:
        return result

    # O01 campos diretos sob <IPI>
    result["ipi_cl_enq"] = _text(ipi_el, "clEnq")
    result["ipi_cnpj_prod"] = _text(ipi_el, "CNPJProd")
    result["ipi_c_selo"] = _text(ipi_el, "cSelo")
    result["ipi_q_selo"] = _fval(ipi_el, "qSelo")
    result["ipi_c_enq"] = _text(ipi_el, "cEnq")

    # Grupo IPITrib (CST 00,49,50,99) ou IPINT (CST 01-05,51-55)
    ipi_trib = _find_direct(ipi_el, "IPITrib")
    ipint = _find_direct(ipi_el, "IPINT")
    group = ipi_trib or ipint

    if group is not None:
        result["ipi_cst"] = _text(group, "CST")
        if ipi_trib is not None:
            # cálculo por alíquota
            result["ipi_v_bc"] = _fval(group, "vBC")
            result["ipi_p_ipi"] = _fval(group, "pIPI")
            # cálculo por valor por unidade
            result["ipi_q_unid"] = _fval(group, "qUnid")
            result["ipi_v_unid"] = _fval(group, "vUnid")
            result["ipi_v_ipi"] = _fval(group, "vIPI")

    return result


def _parse_ii(imposto_el):
    """
    Extrai os campos do Imposto de Importação do elemento <imposto>.
    Retorna um dict com os campos populados (0.0 quando ausentes).
    """
    result = {}

    if imposto_el is None:
        return result

    ii_el = _find_direct(imposto_el, "II")
    if ii_el is None:
        return result

    result["ii_v_bc"] = _fval(ii_el, "vBC")
    result["ii_v_desp_adu"] = _fval(ii_el, "vDespAdu")
    result["ii_v_ii"] = _fval(ii_el, "vII")
    result["ii_v_iof"] = _fval(ii_el, "vIOF")

    return result


def _parse_pis(imposto_el):
    """
    Extrai os campos de PIS do elemento <imposto>.
    Suporta grupos PISAliq, PISQtde, PISNT e PISOutr.
    Retorna um dict com os campos populados (0.0 / None quando ausentes).
    """
    result = {}

    if imposto_el is None:
        return result

    pis_el = _find_direct(imposto_el, "PIS")
    if pis_el is None:
        return result

    # Localizar o grupo ativo
    group = (
        _find_direct(pis_el, "PISAliq")
        or _find_direct(pis_el, "PISQtde")
        or _find_direct(pis_el, "PISNT")
        or _find_direct(pis_el, "PISOutr")
    )
    if group is None:
        return result

    result["pis_cst"] = _text(group, "CST")
    result["pis_v_bc"] = _fval(group, "vBC")
    result["pis_p_pis"] = _fval(group, "pPIS")
    result["pis_q_bc_prod"] = _fval(group, "qBCProd")
    result["pis_v_aliq_prod"] = _fval(group, "vAliqProd")
    result["pis_v_pis"] = _fval(group, "vPIS")

    return result


def _parse_pisst(imposto_el):
    """
    Extrai os campos de PIS ST do elemento <imposto>.
    Todos os campos são filhos diretos de <PISST>.
    Retorna um dict com os campos populados (0.0 / None quando ausentes).
    """
    result = {}

    if imposto_el is None:
        return result

    pisst_el = _find_direct(imposto_el, "PISST")
    if pisst_el is None:
        return result

    result["pisst_v_bc"] = _fval(pisst_el, "vBC")
    result["pisst_p_pis"] = _fval(pisst_el, "pPIS")
    result["pisst_q_bc_prod"] = _fval(pisst_el, "qBCProd")
    result["pisst_v_aliq_prod"] = _fval(pisst_el, "vAliqProd")
    result["pisst_v_pis"] = _fval(pisst_el, "vPIS")

    return result


def _parse_cofins(imposto_el):
    """
    Extrai os campos de COFINS do elemento <imposto>.
    Suporta grupos COFINSAliq, COFINSQtde, COFINSNT e COFINSOutr.
    Retorna um dict com os campos populados (0.0 / None quando ausentes).
    """
    result = {}

    if imposto_el is None:
        return result

    cofins_el = _find_direct(imposto_el, "COFINS")
    if cofins_el is None:
        return result

    group = (
        _find_direct(cofins_el, "COFINSAliq")
        or _find_direct(cofins_el, "COFINSQtde")
        or _find_direct(cofins_el, "COFINSNT")
        or _find_direct(cofins_el, "COFINSOutr")
    )
    if group is None:
        return result

    result["cofins_cst"] = _text(group, "CST")
    result["cofins_v_bc"] = _fval(group, "vBC")
    result["cofins_p_cofins"] = _fval(group, "pCOFINS")
    result["cofins_q_bc_prod"] = _fval(group, "qBCProd")
    result["cofins_v_aliq_prod"] = _fval(group, "vAliqProd")
    result["cofins_v_cofins"] = _fval(group, "vCOFINS")

    return result


def _parse_cofinsst(imposto_el):
    """
    Extrai os campos de COFINS ST do elemento <imposto>.
    Todos os campos são filhos diretos de <COFINSST>.
    Retorna um dict com os campos populados (0.0 / None quando ausentes).
    """
    result = {}

    if imposto_el is None:
        return result

    cofinsst_el = _find_direct(imposto_el, "COFINSST")
    if cofinsst_el is None:
        return result

    result["cofinsst_v_bc"] = _fval(cofinsst_el, "vBC")
    result["cofinsst_p_cofins"] = _fval(cofinsst_el, "pCOFINS")
    result["cofinsst_q_bc_prod"] = _fval(cofinsst_el, "qBCProd")
    result["cofinsst_v_aliq_prod"] = _fval(cofinsst_el, "vAliqProd")
    result["cofinsst_v_cofins"] = _fval(cofinsst_el, "vCOFINS")

    return result


def _parse_imposto_devol(det_el):
    """
    Extrai os campos de impostoDevol do elemento <det>.
    Retorna um dict com os campos populados (0.0 / None quando ausentes).
    """
    result = {}

    if det_el is None:
        return result

    devol_el = _find_direct(det_el, "impostoDevol")
    if devol_el is None:
        return result

    result["devol_p_devol"] = _fval(devol_el, "pDevol")

    ipi_el = _find_direct(devol_el, "IPI")
    if ipi_el is not None:
        result["devol_v_ipi_devol"] = _fval(ipi_el, "vIPIDevol")

    return result


def _parse_icms_uf_dest(imposto_el):
    """
    Extrai os campos do grupo ICMSUFDest do elemento <imposto>.
    Utilizado em vendas interestaduais para consumidor final não contribuinte.
    Retorna um dict com os campos populados (0.0 quando ausentes).
    """
    result = {}

    if imposto_el is None:
        return result

    uf_dest = _find_direct(imposto_el, "ICMSUFDest")
    if uf_dest is None:
        return result

    result["icms_ufdest_v_bc_uf_dest"] = _fval(uf_dest, "vBCUFDest")
    result["icms_ufdest_v_bc_fcp_uf_dest"] = _fval(uf_dest, "vBCFCPUFDest")
    result["icms_ufdest_p_fcp_uf_dest"] = _fval(uf_dest, "pFCPUFDest")
    result["icms_ufdest_p_icms_uf_dest"] = _fval(uf_dest, "pICMSUFDest")
    result["icms_ufdest_p_icms_inter"] = _fval(uf_dest, "pICMSInter")
    result["icms_ufdest_p_icms_inter_part"] = _fval(uf_dest, "pICMSInterPart")
    result["icms_ufdest_v_fcp_uf_dest"] = _fval(uf_dest, "vFCPUFDest")
    result["icms_ufdest_v_icms_uf_dest"] = _fval(uf_dest, "vICMSUFDest")
    result["icms_ufdest_v_icms_uf_remet"] = _fval(uf_dest, "vICMSUFRemet")

    return result


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

    # ── IPI ───────────────────────────────────────────────────────────────
    # O02 – Classe de enquadramento do IPI para Cigarros e Bebidas (1-5)
    ipi_cl_enq = fields.Char(string="Classe Enquadramento IPI", size=5, readonly=True)
    # O03 – CNPJ do produtor da mercadoria (14)
    ipi_cnpj_prod = fields.Char(string="CNPJ Produtor IPI", size=14, readonly=True)
    # O04 – Código do selo de controle IPI (1-60)
    ipi_c_selo = fields.Char(string="Cód. Selo IPI", size=60, readonly=True)
    # O05 – Quantidade de selo de controle (1-12)
    ipi_q_selo = fields.Float(string="Qtd. Selo IPI", digits=(12, 0), readonly=True)
    # O06 – Código de Enquadramento Legal do IPI (1-3)
    ipi_c_enq = fields.Char(
        string="Cód. Enquadramento Legal IPI", size=3, readonly=True
    )
    # O09 – Código da situação tributária do IPI (CST) — válido para IPITrib e IPINT
    ipi_cst = fields.Char(string="CST IPI", size=2, readonly=True)
    # O10 – Valor da BC do IPI (13v2) — apenas IPITrib
    ipi_v_bc = fields.Float(string="BC IPI", digits=(13, 2), readonly=True)
    # O13 – Alíquota do IPI (3v2-4) — apenas IPITrib, cálculo por alíquota
    ipi_p_ipi = fields.Float(string="Alíq. IPI", digits=(5, 4), readonly=True)
    # O11 – Quantidade total na unidade padrão para tributação (12v0-4) — IPITrib, cálculo por valor/unidade
    ipi_q_unid = fields.Float(string="Qtd. Unid. IPI", digits=(12, 4), readonly=True)
    # O12 – Valor por Unidade Tributável (11v0-4) — IPITrib, cálculo por valor/unidade
    ipi_v_unid = fields.Float(string="Vlr. Unit. IPI", digits=(11, 4), readonly=True)
    # O14 – Valor do IPI (13v2)
    ipi_v_ipi = fields.Float(string="Vlr. IPI", digits=(13, 2), readonly=True)

    # ── Imposto de Importação ─────────────────────────────────────────────
    # P02 – Valor da BC do Imposto de Importação (13v2)
    ii_v_bc = fields.Float(string="BC Imp. Importação", digits=(13, 2), readonly=True)
    # P03 – Valor das despesas aduaneiras (13v2)
    ii_v_desp_adu = fields.Float(
        string="Despesas Aduaneiras", digits=(13, 2), readonly=True
    )
    # P04 – Valor do Imposto de Importação (13v2)
    ii_v_ii = fields.Float(string="Vlr. Imp. Importação", digits=(13, 2), readonly=True)
    # P05 – Valor do Imposto sobre Operações Financeiras (13v2)
    ii_v_iof = fields.Float(string="Vlr. IOF", digits=(13, 2), readonly=True)

    # ── PIS ───────────────────────────────────────────────────────────────
    # Q06 – Código de Situação Tributária do PIS (2) — comum a todos os grupos
    pis_cst = fields.Char(string="CST PIS", size=2, readonly=True)
    # Q07 – Valor da BC do PIS (13v2) — PISAliq / PISOutr (cálculo por %)
    pis_v_bc = fields.Float(string="BC PIS", digits=(13, 2), readonly=True)
    # Q08 – Alíquota do PIS em percentual (3v2-4) — PISAliq / PISOutr (cálculo por %)
    pis_p_pis = fields.Float(string="Alíq. PIS %", digits=(5, 4), readonly=True)
    # Q10 – Quantidade vendida (12v0-4) — PISQtde / PISOutr (cálculo por qtde)
    pis_q_bc_prod = fields.Float(
        string="Qtd. Vendida PIS", digits=(12, 4), readonly=True
    )
    # Q11 – Alíquota do PIS em reais (11v0-4) — PISQtde / PISOutr (cálculo por qtde)
    pis_v_aliq_prod = fields.Float(string="Alíq. PIS R$", digits=(11, 4), readonly=True)
    # Q09 – Valor do PIS (13v2) — comum a PISAliq, PISQtde e PISOutr
    pis_v_pis = fields.Float(string="Vlr. PIS", digits=(13, 2), readonly=True)

    # ── PIS ST ────────────────────────────────────────────────────────────
    # R02 – Valor da BC do PIS ST (13v2) — cálculo por %
    pisst_v_bc = fields.Float(string="BC PIS ST", digits=(13, 2), readonly=True)
    # R03 – Alíquota do PIS ST em percentual (3v2-4) — cálculo por %
    pisst_p_pis = fields.Float(string="Alíq. PIS ST %", digits=(5, 4), readonly=True)
    # R04 – Quantidade vendida (12v0-4) — cálculo por valor
    pisst_q_bc_prod = fields.Float(
        string="Qtd. Vendida PIS ST", digits=(12, 4), readonly=True
    )
    # R05 – Alíquota do PIS ST em reais (11v0-4) — cálculo por valor
    pisst_v_aliq_prod = fields.Float(
        string="Alíq. PIS ST R$", digits=(11, 4), readonly=True
    )
    # R06 – Valor do PIS ST (13v2)
    pisst_v_pis = fields.Float(string="Vlr. PIS ST", digits=(13, 2), readonly=True)

    # ── COFINS ────────────────────────────────────────────────────────────
    # S06 – Código de Situação Tributária da COFINS (2) — comum a todos os grupos
    cofins_cst = fields.Char(string="CST COFINS", size=2, readonly=True)
    # S07 – Valor da BC da COFINS (13v2) — COFINSAliq / COFINSOutr (cálculo por %)
    cofins_v_bc = fields.Float(string="BC COFINS", digits=(13, 2), readonly=True)
    # S08 – Alíquota da COFINS em percentual (3v2-4) — COFINSAliq / COFINSOutr (cálculo por %)
    cofins_p_cofins = fields.Float(
        string="Alíq. COFINS %", digits=(5, 4), readonly=True
    )
    # S09 – Quantidade vendida (12v0-4) — COFINSQtde / COFINSOutr (cálculo por qtde)
    cofins_q_bc_prod = fields.Float(
        string="Qtd. Vendida COFINS", digits=(12, 4), readonly=True
    )
    # S10 – Alíquota da COFINS em reais (11v0-4) — COFINSQtde / COFINSOutr (cálculo por qtde)
    cofins_v_aliq_prod = fields.Float(
        string="Alíq. COFINS R$", digits=(11, 4), readonly=True
    )
    # S11 – Valor da COFINS (13v2) — comum a COFINSAliq, COFINSQtde e COFINSOutr
    cofins_v_cofins = fields.Float(string="Vlr. COFINS", digits=(13, 2), readonly=True)

    # ── COFINS ST ─────────────────────────────────────────────────────────
    # T02 – Valor da BC da COFINS ST (13v2) — cálculo por %
    cofinsst_v_bc = fields.Float(string="BC COFINS ST", digits=(13, 2), readonly=True)
    # T03 – Alíquota da COFINS ST em percentual (3v2-4) — cálculo por %
    cofinsst_p_cofins = fields.Float(
        string="Alíq. COFINS ST %", digits=(5, 4), readonly=True
    )
    # T04 – Quantidade vendida (12v0-4) — cálculo por valor
    cofinsst_q_bc_prod = fields.Float(
        string="Qtd. Vendida COFINS ST", digits=(12, 4), readonly=True
    )
    # T05 – Alíquota da COFINS ST em reais (11v0-4) — cálculo por valor
    cofinsst_v_aliq_prod = fields.Float(
        string="Alíq. COFINS ST R$", digits=(11, 4), readonly=True
    )
    # T06 – Valor da COFINS ST (13v2)
    cofinsst_v_cofins = fields.Float(
        string="Vlr. COFINS ST", digits=(13, 2), readonly=True
    )

    # ── Imposto Devolvido (impostoDevol) ──────────────────────────────────
    # UA02 – Percentual da mercadoria devolvida (3v2)
    devol_p_devol = fields.Float(string="% Devolvido", digits=(5, 2), readonly=True)
    # UA04 – Valor do IPI devolvido (13v2)
    devol_v_ipi_devol = fields.Float(
        string="Vlr. IPI Devolvido", digits=(13, 2), readonly=True
    )

    # ── Informações Adicionais do Produto ─────────────────────────────────
    # V01 – Informações adicionais do produto (1-500)
    inf_ad_prod = fields.Char(string="Inf. Adicionais Produto", size=500, readonly=True)

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
        vals.update(_parse_ipi(imposto))
        vals.update(_parse_ii(imposto))
        vals.update(_parse_pis(imposto))
        vals.update(_parse_pisst(imposto))
        vals.update(_parse_cofins(imposto))
        vals.update(_parse_cofinsst(imposto))
        vals.update(_parse_imposto_devol(det_el))
        vals["inf_ad_prod"] = _text(det_el, "infAdProd")

        return self.create(vals)
