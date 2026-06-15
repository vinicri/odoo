"""
Brazilian DFe Monitor - NF-e Processada (procNFe)

Armazena os dados extraídos do XML procNFe recebido via NFeDistribuicaoDFe.
O procNFe contém a NF-e completa (infNFe) + protocolo de autorização (protNFe).
"""

import base64
import logging
from datetime import datetime, timezone
from lxml import etree
from odoo import api, fields, models, _

_logger = logging.getLogger(__name__)

NS = "http://www.portalfiscal.inf.br/nfe"


def _parse_nfe_dh(s):
    """Parse de data/hora ISO-8601 com offset (ex. -03:00 ou Z) para UTC naive (Odoo Datetime)."""
    if not s:
        return None
    s = s.strip().replace("Z", "+00:00")
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def _find(root, *tags):
    """Busca um elemento pelo primeiro tag encontrado, com ou sem namespace."""
    for tag in tags:
        el = root.find(f"{{{NS}}}{tag}")
        if el is not None:
            return el
        el = root.find(f".//{{{NS}}}{tag}")
        if el is not None:
            return el
    return None


def _text(root, *tags):
    el = _find(root, *tags)
    return el.text if el is not None else None


class DfeProcNfe(models.Model):
    _name = "l10n_br_dfe_monitor.proc_nfe"
    _description = "NF-e Processada (procNFe)"
    _order = "dh_emi desc, id desc"
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
    res_nfe_id = fields.Many2one(
        "l10n_br_dfe_monitor.res_nfe",
        string="Resumo NF-e",
        ondelete="set null",
        index=True,
        readonly=True,
    )

    # ── Escrituração ────────────────────────────────────────────────────────
    estado_escrituracao = fields.Selection(
        [("pendente", "Pendente"), ("escriturado", "Escriturado")],
        string="Escrituração",
        default="pendente",
        required=True,
        index=True,
    )

    tp_amb = fields.Selection(
        [("1", "Produção"), ("2", "Homologação")],
        string="Tipo de Ambiente",
        readonly=True,
        required=True,
    )

    # ── Grupo A/B – Identificação da NF-e ──────────────────────────────────
    versao = fields.Char(string="Versão", readonly=True, required=True)
    ch_nfe = fields.Char(
        string="Chave de Acesso", size=44, index=True, readonly=True, required=True
    )
    c_uf = fields.Char(string="UF Emitente (cód)", size=2, readonly=True, required=True)
    nat_op = fields.Char(string="Natureza da Operação", readonly=True, required=True)
    mod = fields.Char(string="Modelo", size=2, readonly=True, required=True)
    serie = fields.Char(string="Série", size=3, readonly=True, required=True)
    n_nf = fields.Char(string="Número NF", readonly=True, required=True)
    dh_emi = fields.Datetime(string="Data de Emissão", readonly=True, required=True)
    dh_sai_ent = fields.Datetime(string="Data Saída/Entrada", readonly=True)
    tp_nf = fields.Selection(
        [("0", "Entrada"), ("1", "Saída")],
        string="Tipo de Operação",
        readonly=True,
        required=True,
    )
    id_dest = fields.Selection(
        [("1", "Interna"), ("2", "Interestadual"), ("3", "Exterior")],
        string="Destino",
        readonly=True,
        required=True,
    )
    c_mun_fg = fields.Char(
        string="Código do Município do Fato Gerador", readonly=True, required=True
    )
    tp_imp = fields.Selection(
        [
            ("0", "Sem DANFE"),
            ("1", "DANFE Retrato"),
            ("2", "DANFE Paisagem"),
            ("3", "DANFE Simplificado"),
            ("4", "DANFE NFC-e"),
            ("5", "DANFE NFC-e em mensagem eletrônica"),
        ],
        string="Tipo de Impresso",
        readonly=True,
    )

    tp_emis = fields.Selection(
        [
            ("1", "Normal"),
            ("2", "Contingência FS"),
            ("3", "Regime Especial NFF"),
            ("4", "Contingência DPEC"),
            ("5", "Contingência FSDA"),
            ("6", "Contingência SVC - AN"),
            ("7", "Contingência SVC - RS"),
            ("9", "Contingência off-line NFC-e"),
        ],
        string="Tipo de Emissão",
        readonly=True,
    )

    fin_nfe = fields.Selection(
        [
            ("1", "Normal"),
            ("2", "Complementar"),
            ("3", "Ajuste"),
            ("4", "Devolução"),
        ],
        string="Finalidade",
        readonly=True,
    )
    ind_final = fields.Selection(
        [("0", "Normal"), ("1", "Consumidor Final")],
        string="Consumidor Final",
        readonly=True,
    )
    ind_pres = fields.Selection(
        [
            ("0", "Não se aplica"),
            ("1", "Presencial"),
            ("2", "Internet"),
            ("3", "Teleatendimento"),
            ("4", "Domicílio NFC-e"),
            ("5", "Presencial fora estab."),
            ("9", "Outros"),
        ],
        string="Presença Comprador",
        readonly=True,
    )

    ind_intermed = fields.Selection(
        [("0", "Operação sem intermediador"), ("1", "Operação com intermediador")],
        string="Intermediador",
        readonly=True,
    )

    proc_emi = fields.Selection(
        [
            ("0", "Emissão de NF-e com aplicativo do contribuinte"),
            ("1", "Emissão de NF-e avulsa pelo Fisco"),
            (
                "2",
                "Emissão de NF-e avulsa, pelo contribuinte com seu certificado digital, através do site do Fisco",
            ),
            ("3", "Emissão NF-e pelo contribuinte com aplicativo fornecido pelo Fisco"),
        ],
        string="Processo de Emissão",
        readonly=True,
    )

    # TODO documento referenciado

    # ── Grupo C – Emitente ─────────────────────────────────────────────────
    emit_cnpj = fields.Char(string="CNPJ Emitente", size=14, readonly=True)
    emit_cpf = fields.Char(string="CPF Emitente", size=11, readonly=True)
    emit_x_nome = fields.Char(
        string="Razão Social Emitente", readonly=True, required=True
    )
    emit_x_fant = fields.Char(string="Nome Fantasia Emitente", readonly=True)
    emit_ender_x_lgr = fields.Char(
        string="Endereço Emitente", readonly=True, required=True
    )
    emit_ender_nro = fields.Char(string="Número Emitente", readonly=True, required=True)
    emit_ender_xCpl = fields.Char(string="Complemento Emitente", readonly=True)
    emit_ender_xBairro = fields.Char(
        string="Bairro Emitente", readonly=True, required=True
    )
    emit_ender_cMun = fields.Char(
        string="Codigo do Municipio Emitente", readonly=True, required=True
    )
    emit_ender_xMun = fields.Char(
        string="Município Emitente", readonly=True, required=True
    )
    emit_ender_UF = fields.Char(
        string="UF Emitente", size=2, readonly=True, required=True
    )
    emit_ender_CEP = fields.Char(string="CEP Emitente", readonly=True, required=True)
    emit_ender_cPais = fields.Char(string="Codigo do Pais Emitente", readonly=True)
    emit_ender_xPais = fields.Char(string="Pais Emitente", readonly=True)

    emit_ender_fone = fields.Char(string="Telefone Emitente", readonly=True)

    emit_ie = fields.Char(string="IE Emitente", readonly=True, required=True)
    emit_iest = fields.Char(string="IE Substituto Tributário Emitente", readonly=True)
    emit_im = fields.Char(string="IM Emitente", readonly=True)
    emit_cnae = fields.Char(string="CNAE Emitente", readonly=True)
    emit_crt = fields.Selection(
        [
            ("1", "Simples Nacional"),
            ("2", "Simples Nacional – excesso"),
            ("3", "Regime Normal"),
        ],
        string="CRT Emitente",
        readonly=True,
        required=True,
    )

    # ── Grupo E – Destinatário ─────────────────────────────────────────────
    dest_cnpj = fields.Char(string="CNPJ Destinatário", size=14, readonly=True)
    dest_cpf = fields.Char(string="CPF Destinatário", size=11, readonly=True)
    dest_id_estrangeiro = fields.Char(
        string="ID Estrangeiro Destinatário", readonly=True
    )
    dest_x_nome = fields.Char(string="Nome Destinatário", readonly=True)

    dest_ender_x_lgr = fields.Char(string="Endereço Destinatário", readonly=True)
    dest_ender_nro = fields.Char(string="Número Destinatário", readonly=True)
    dest_ender_xCpl = fields.Char(string="Complemento Destinatário", readonly=True)
    dest_ender_xBairro = fields.Char(string="Bairro Destinatário", readonly=True)
    dest_ender_cMun = fields.Char(
        string="Codigo do Municipio Destinatário", readonly=True
    )
    dest_ender_xMun = fields.Char(string="Município Destinatário", readonly=True)
    dest_ender_UF = fields.Char(string="UF Destinatário", size=2, readonly=True)
    dest_ender_CEP = fields.Char(string="CEP Destinatário", readonly=True)
    dest_ender_cPais = fields.Char(string="Codigo do Pais Destinatário", readonly=True)
    dest_ender_xPais = fields.Char(string="Pais Destinatário", readonly=True)

    dest_ender_fone = fields.Char(string="Telefone Destinatário", readonly=True)
    dest_email = fields.Char(string="E-mail Destinatário", readonly=True)

    dest_ind_ie = fields.Selection(
        [
            ("1", "Contribuinte ICMS (informar a IE do destinatário)"),
            ("2", "Contribuinte isento de Inscrição no cadastro de Contribuintes"),
            (
                "9",
                "Não Contribuinte (pode ou não possuir IE no Cadastro de Contribuintes do ICMS)",
            ),
        ],
        string="Indicador da IE do Destinatário",
        readonly=True,
    )

    dest_ie = fields.Char(string="IE Destinatário", readonly=True)
    dest_isuf = fields.Char(string="SUFRAMA Destinatário", readonly=True)
    dest_im = fields.Char(string="Inscrição Municipal Destinatário", readonly=True)

    # TODO dados cobranca
    # TODO pagamento
    # TODO intermediador
    # TODO inf adicionais
    # TODO info comercio exterior
    # ── Grupo X – Transporte ───────────────────────────────────────────────
    # X02 – Modalidade do frete
    transp_mod_frete = fields.Selection(
        [
            ("0", "CIF (por conta do Remetente)"),
            ("1", "FOB (por conta do Destinatário)"),
            ("2", "Por conta de Terceiros"),
            ("3", "Transporte Próprio por conta do Remetente"),
            ("4", "Transporte Próprio por conta do Destinatário"),
            ("9", "Sem Ocorrência de Transporte"),
        ],
        string="Modalidade do Frete",
        readonly=True,
    )
    # X04 – CNPJ do Transportador
    transp_cnpj = fields.Char(string="CNPJ Transportador", size=14, readonly=True)
    # X05 – CPF do Transportador
    transp_cpf = fields.Char(string="CPF Transportador", size=11, readonly=True)
    # X06 – Razão Social ou nome do Transportador
    transp_x_nome = fields.Char(string="Nome Transportador", size=60, readonly=True)
    # X07 – Inscrição Estadual do Transportador
    transp_ie = fields.Char(string="IE Transportador", size=14, readonly=True)
    # X08 – Endereço Completo do Transportador
    transp_x_ender = fields.Char(
        string="Endereço Transportador", size=60, readonly=True
    )
    # X09 – Nome do município do Transportador
    transp_x_mun = fields.Char(string="Município Transportador", size=60, readonly=True)
    # X10 – UF do Transportador
    transp_uf = fields.Char(string="UF Transportador", size=2, readonly=True)
    # X12 – Valor do Serviço de transporte (retenção ICMS)
    transp_v_serv = fields.Float(
        string="Vlr. Serviço Transp.", digits=(13, 2), readonly=True
    )
    # X13 – BC da Retenção do ICMS transporte
    transp_v_bc_ret = fields.Float(
        string="BC Ret. ICMS Transp.", digits=(13, 2), readonly=True
    )
    # X14 – Alíquota da Retenção do ICMS transporte (3v2-4)
    transp_p_icms_ret = fields.Float(
        string="Alíq. Ret. ICMS Transp.", digits=(5, 4), readonly=True
    )
    # X15 – Valor do ICMS Retido transporte
    transp_v_icms_ret = fields.Float(
        string="Vlr. ICMS Ret. Transp.", digits=(13, 2), readonly=True
    )
    # X16 – CFOP do Serviço de Transporte
    transp_cfop = fields.Char(string="CFOP Transp.", size=4, readonly=True)
    # X17 – Código do município de ocorrência do FG do ICMS transporte
    transp_c_mun_fg = fields.Char(
        string="Cód. Município FG Transp.", size=7, readonly=True
    )
    # X19 – Placa do Veículo de Transporte
    transp_placa = fields.Char(string="Placa Veículo", size=7, readonly=True)
    # X20 – UF do Veículo de Transporte
    transp_uf_veic = fields.Char(string="UF Veículo", size=2, readonly=True)
    # X21 – RNTC do Veículo de Transporte
    transp_rntc = fields.Char(string="RNTC Veículo", size=20, readonly=True)

    # ── Grupo W – Totais ICMS ──────────────────────────────────────────────
    v_bc = fields.Float(
        string="Base Cálculo ICMS", digits=(13, 2), readonly=True, required=True
    )
    v_icms = fields.Float(
        string="Valor ICMS", digits=(13, 2), readonly=True, required=True
    )
    v_icms_deson = fields.Float(
        string="ICMS Desonerado", digits=(13, 2), readonly=True, required=True
    )
    v_fcp_uf_dest = fields.Float(
        string="Valor FCP da UF de Destino",
        digits=(13, 2),
        readonly=True,
    )
    v_icms_uf_dest = fields.Float(
        string="Valor ICMS da UF de Destino",
        digits=(13, 2),
        readonly=True,
    )
    v_icms_uf_remet = fields.Float(
        string="Valor ICMS da UF de Remetente",
        digits=(13, 2),
        readonly=True,
    )
    v_fcp = fields.Float(
        string="Valor FCP", digits=(13, 2), readonly=True, required=True
    )
    v_bc_st = fields.Float(
        string="Base Cálculo ICMS ST", digits=(13, 2), readonly=True, required=True
    )
    v_st = fields.Float(
        string="Valor ICMS ST", digits=(13, 2), readonly=True, required=True
    )
    v_fcp_st = fields.Float(
        string="Valor FCP ST", digits=(13, 2), readonly=True, required=True
    )
    v_fcp_st_ret = fields.Float(
        string="Valor FCP ST Retido", digits=(13, 2), readonly=True, required=True
    )
    v_prod = fields.Float(
        string="Valor Produtos/Serviços", digits=(13, 2), readonly=True, required=True
    )
    v_frete = fields.Float(string="Frete", digits=(13, 2), readonly=True, required=True)
    v_seg = fields.Float(string="Seguro", digits=(13, 2), readonly=True, required=True)
    v_desc = fields.Float(
        string="Desconto", digits=(13, 2), readonly=True, required=True
    )
    v_ii = fields.Float(
        string="Imposto Importação", digits=(13, 2), readonly=True, required=True
    )
    v_ipi = fields.Float(string="IPI", digits=(13, 2), readonly=True, required=True)
    v_ipi_devol = fields.Float(
        string="IPI Devolvido", digits=(13, 2), readonly=True, required=True
    )
    v_pis = fields.Float(string="PIS", digits=(13, 2), readonly=True, required=True)
    v_cofins = fields.Float(
        string="COFINS", digits=(13, 2), readonly=True, required=True
    )
    v_outro = fields.Float(
        string="Outras Despesas", digits=(13, 2), readonly=True, required=True
    )
    v_nf = fields.Float(
        string="Valor Total NF-e", digits=(13, 2), readonly=True, required=True
    )
    v_tot_trib = fields.Float(string="Aprox. Tributos", digits=(13, 2), readonly=True)

    # ── Protocolo de Autorização (protNFe) ─────────────────────────────────
    # n_prot = fields.Char(string="Número Protocolo", readonly=True)
    # dh_recbto = fields.Datetime(string="Data Autorização", readonly=True)
    # c_stat = fields.Char(string="Código Status (cStat)", size=3, readonly=True)
    # x_motivo = fields.Char(string="Motivo Status", readonly=True)
    # dig_val = fields.Char(string="Digest Value", readonly=True)

    # ── Informações adicionais ─────────────────────────────────────────────
    inf_cpl = fields.Text(string="Informações Complementares", readonly=True)
    inf_ad_fisco = fields.Text(string="Inf. de Interesse do Fisco", readonly=True)

    # ── Grupo YA – Pagamento ───────────────────────────────────────────────
    # YA09 – Valor do troco (13v2)
    pag_v_troco = fields.Float(string="Troco", digits=(13, 2), readonly=True)

    pag_ids = fields.One2many(
        "l10n_br_dfe_monitor.proc_nfe_pag",
        "proc_nfe_id",
        string="Pagamentos",
        readonly=True,
    )

    # ── Grupo YB – Intermediador ───────────────────────────────────────────
    # YB02 – CNPJ do Intermediador (14)
    intermed_cnpj = fields.Char(string="CNPJ Intermediador", size=14, readonly=True)
    # YB03 – Identificador cadastrado no intermediador (60)
    intermed_id_cad_int_tran = fields.Char(
        string="ID Intermediador", size=60, readonly=True
    )

    # ── Grupo Y – Cobrança ─────────────────────────────────────────────────
    # Y03 – Número da Fatura (1-60)
    fat_n_fat = fields.Char(string="Nº Fatura", size=60, readonly=True)
    # Y04 – Valor Original da Fatura (13v2)
    fat_v_orig = fields.Float(
        string="Vlr. Original Fatura", digits=(13, 2), readonly=True
    )
    # Y05 – Valor do Desconto da Fatura (13v2)
    fat_v_desc = fields.Float(string="Desc. Fatura", digits=(13, 2), readonly=True)
    # Y06 – Valor Líquido da Fatura (13v2)
    fat_v_liq = fields.Float(
        string="Vlr. Líquido Fatura", digits=(13, 2), readonly=True
    )

    dup_ids = fields.One2many(
        "l10n_br_dfe_monitor.proc_nfe_dup",
        "proc_nfe_id",
        string="Parcelas",
        readonly=True,
    )

    # ── Itens ───────────────────────────────────────────────────────────────
    item_ids = fields.One2many(
        "l10n_br_dfe_monitor.proc_nfe_item",
        "proc_nfe_id",
        string="Itens",
        readonly=True,
    )

    # ── Manifestação do destinatário ───────────────────────────────────────
    # manifestacao = fields.Selection(
    #     [
    #         ("ciencia", "Ciência da Operação"),
    #         ("confirmado", "Confirmação da Operação"),
    #         ("nao_realizada", "Operação Não Realizada"),
    #         ("desconhecido", "Desconhecimento da Operação"),
    #     ],
    #     string="Manifestação do Destinatário",
    # )

    dfe_proc_evento_nfe_ids = fields.One2many(
        "l10n_br_dfe_monitor.proc_evento_nfe",
        "proc_nfe_id",
        string="Eventos de NF-e",
        readonly=True,
    )

    # On the proc_nfe model
    dfe_nfe_escrit_id = fields.One2many(
        "l10n_br_dfe_monitor.dfe_nfe_escrit",
        "proc_nfe_id",
        string="Escrituração",
        readonly=True,
    )

    partner_id = fields.Many2one(
        "res.partner",
        string="Parceiro Emitente",
        store=True,
        readonly=False,
        index=True,
    )

    def action_nfe_escrit(self):
        self.ensure_one()
        vat = self.emit_cnpj or self.emit_cpf
        partner = (
            self.env["res.partner"].search([("vat", "=", vat)], limit=1)
            if vat
            else False
        )
        if not partner:
            return self._action_create_partner()
        return {
            "type": "ir.actions.act_window",
            "name": _("Escrituração de NF-e"),
            "res_model": "l10n_br_dfe_monitor.dfe_nfe_escrit",
            "context": {"default_proc_nfe_id": self.id},
            "view_mode": "form",
            "target": "new",
        }

    def _action_create_partner(self):
        self.ensure_one()
        state_id = False
        if self.emit_ender_UF:
            state = self.env["res.country.state"].search(
                [("code", "=", self.emit_ender_UF), ("country_id.code", "=", "BR")],
                limit=1,
            )
            state_id = state.id if state else False

        country_id = False
        if self.emit_ender_cPais:
            country = self.env["res.country"].search(
                [("bacen_code", "=", self.emit_ender_cPais)],
                limit=1,
            )
            country_id = (
                country.id
                if country
                else self.env.ref("base.br", raise_if_not_found=False)
            )

        city_id = False
        if self.emit_ender_cMun:
            city = self.env["res.city"].search(
                [("ibge_code", "=", self.emit_ender_cMun)],
                limit=1,
            )
            city_id = city.id if city else False

        cnae_id = False
        if self.emit_cnae:
            cnae = self.env["l10n_br_fiscal.cnae"].search(
                [("code_num", "=", self.emit_cnae)],
                limit=1,
            )
            cnae_id = cnae.id if cnae else False

        context = {
            "default_proc_nfe_id": self.id,
            "default_vat": self.emit_cnpj or self.emit_cpf or "",
            "default_legal_name": self.emit_x_nome or "",
            "default_trade_name": self.emit_x_fant or "",
            "default_name": self.emit_x_fant or self.emit_x_nome or "",
            # Endereço
            "default_street": self.emit_ender_x_lgr or "",
            "default_street_number": self.emit_ender_nro or "",
            "default_street_complement": self.emit_ender_xCpl or "",
            "default_district": self.emit_ender_xBairro or "",
            "default_zip": self.emit_ender_CEP or "",
            "default_phone": self.emit_ender_fone or "",
            # Cadastro Fiscal
            "default_inscr_est": self.emit_ie or "",
            "default_inscr_mun": self.emit_im or "",
            "default_main_cnae_id": cnae_id,
            "default_fiscal_framework": self.emit_crt or "",
            # Localização
            "default_city_id": city_id,
            "default_state_id": state_id,
            "default_country_id": country_id,
        }
        return {
            "type": "ir.actions.act_window",
            "name": _("Criar Parceiro Emitente"),
            "res_model": "l10n_br_dfe_monitor.create_partner_wizard",
            "view_mode": "form",
            "target": "new",
            "context": context,
        }

    def link_partner(self, partner):
        self.partner_id = partner

    @api.model
    def _create_from_dfe_document(self, dfe_doc):
        """
        Cria um registro procNFe a partir de um DfeDocument com schema procNFe.
        Retorna o registro criado ou None em caso de erro.
        """
        try:
            if not dfe_doc.xml_file:
                _logger.warning(f"DFe {dfe_doc.nsu}: xml_file vazio, ignorando.")
                return None

            raw_xml = base64.b64decode(dfe_doc.xml_file)
            root = etree.fromstring(raw_xml)

            # ── infNFe / ide / emit / dest / total / infAdic ────────────────────
            nfe = _find(root, "NFe")
            if nfe is None:
                raise ValueError(f"DFe {dfe_doc.nsu}: elemento NFe não encontrado.")

            inf_nfe = _find(nfe, "infNFe")
            if inf_nfe is None:
                raise ValueError(f"DFe {dfe_doc.nsu}: elemento infNFe não encontrado.")

            versao = inf_nfe.get("versao")
            ch_nfe = (inf_nfe.get("Id") or "").replace("NFe", "") or _text(
                inf_nfe, "chNFe"
            )

            # Grupo B – Identificação
            ide = _find(inf_nfe, "ide")
            if ide is None:
                raise ValueError(f"DFe {dfe_doc.nsu}: elemento ide não encontrado.")

            c_uf = _text(ide, "cUF")
            nat_op = _text(ide, "natOp")
            mod = _text(ide, "mod")
            serie = _text(ide, "serie")
            n_nf = _text(ide, "nNF")
            dh_emi = _parse_nfe_dh(_text(ide, "dhEmi"))
            dh_sai_ent = _parse_nfe_dh(_text(ide, "dhSaiEnt"))
            tp_nf = _text(ide, "tpNF")
            id_dest = _text(ide, "idDest")
            c_mun_fg = _text(ide, "cMunFG")
            tp_imp = _text(ide, "tpImp")
            tp_emis = _text(ide, "tpEmis")
            tp_amb = _text(ide, "tpAmb")
            fin_nfe = _text(ide, "finNFe")
            ind_final = _text(ide, "indFinal")
            ind_pres = _text(ide, "indPres")
            ind_intermed = _text(ide, "indIntermed")
            proc_emi = _text(ide, "procEmi")

            # Grupo C – Emitente
            emit = _find(inf_nfe, "emit")
            if emit is None:
                raise ValueError(f"DFe {dfe_doc.nsu}: elemento emit não encontrado.")

            emit_cnpj = _text(emit, "CNPJ")
            emit_cpf = _text(emit, "CPF")
            emit_x_nome = _text(emit, "xNome")
            emit_x_fant = _text(emit, "xFant")

            emit_ie = _text(emit, "IE")
            emit_iest = _text(emit, "IEST")
            emit_im = _text(emit, "IM")
            emit_cnae = _text(emit, "CNAE")
            emit_crt = _text(emit, "CRT")

            ender_emit = _find(emit, "enderEmit")
            if ender_emit is None:
                raise ValueError(
                    f"DFe {dfe_doc.nsu}: elemento enderEmit não encontrado."
                )

            emit_ender_x_lgr = _text(ender_emit, "xLgr")
            emit_ender_nro = _text(ender_emit, "nro")
            emit_ender_xCpl = _text(ender_emit, "xCpl")
            emit_ender_xBairro = _text(ender_emit, "xBairro")
            emit_ender_cMun = _text(ender_emit, "cMun")
            emit_ender_xMun = _text(ender_emit, "xMun")
            emit_ender_UF = _text(ender_emit, "UF")
            emit_ender_CEP = _text(ender_emit, "CEP")
            emit_ender_cPais = _text(ender_emit, "cPais")
            emit_ender_xPais = _text(ender_emit, "xPais")
            emit_ender_fone = _text(ender_emit, "fone")

            # Grupo E – Destinatário
            dest = _find(inf_nfe, "dest")
            if dest is None:
                raise ValueError(f"DFe {dfe_doc.nsu}: elemento dest não encontrado.")

            dest_cnpj = _text(dest, "CNPJ")
            dest_cpf = _text(dest, "CPF")
            dest_id_estrangeiro = _text(dest, "idEstrangeiro")
            dest_x_nome = _text(dest, "xNome")

            dest_ind_ie = _text(dest, "indIEDest")
            dest_ie = _text(dest, "IE")
            dest_isuf = _text(dest, "ISUF")
            dest_im = _text(dest, "IM")

            dest_x_email = _text(dest, "email")

            ender_dest = _find(dest, "enderDest")
            if ender_dest is not None:
                dest_ender_x_lgr = _text(ender_dest, "xLgr") or None
                dest_ender_nro = _text(ender_dest, "nro") or None
                dest_ender_xCpl = _text(ender_dest, "xCpl") or None
                dest_ender_xBairro = _text(ender_dest, "xBairro") or None
                dest_ender_cMun = _text(ender_dest, "cMun") or None
                dest_ender_xMun = _text(ender_dest, "xMun") or None
                dest_ender_UF = _text(ender_dest, "UF") or None
                dest_ender_CEP = _text(ender_dest, "CEP") or None
                dest_ender_cPais = _text(ender_dest, "cPais") or None
                dest_ender_xPais = _text(ender_dest, "xPais") or None
                dest_ender_fone = _text(ender_dest, "fone") or None

            # Grupo W – Totais
            total = _find(inf_nfe, "total")
            icms_tot = _find(total, "ICMSTot")

            if icms_tot is None:
                raise ValueError(f"DFe {dfe_doc.nsu}: elemento ICMSTot não encontrado.")

            def _fval(el, tag):
                v = _text(el, tag) if el is not None else None
                if v is None:
                    return 0.0
                v = v.strip()
                if not v:
                    return 0.0
                # XML costuma usar ".", mas alguns fluxos podem vir com ","
                v = v.replace(",", ".") if ("," in v and "." not in v) else v
                try:
                    return float(v)
                except (ValueError, TypeError):
                    return 0.0

            v_bc = _fval(icms_tot, "vBC")
            v_icms = _fval(icms_tot, "vICMS")
            v_icms_deson = _fval(icms_tot, "vICMSDeson")
            v_fcp_uf_dest = _fval(icms_tot, "vFCPUFDest")
            v_icms_uf_dest = _fval(icms_tot, "vICMSUFDest")
            v_icms_uf_remet = _fval(icms_tot, "vICMSUFRemet")
            v_fcp = _fval(icms_tot, "vFCP")
            v_bc_st = _fval(icms_tot, "vBCST")
            v_st = _fval(icms_tot, "vST")
            v_fcp_st = _fval(icms_tot, "vFCPST")
            v_fcp_st_ret = _fval(icms_tot, "vFCPSTRet")
            v_prod = _fval(icms_tot, "vProd")
            v_frete = _fval(icms_tot, "vFrete")
            v_seg = _fval(icms_tot, "vSeg")
            v_desc = _fval(icms_tot, "vDesc")
            v_ii = _fval(icms_tot, "vII")
            v_ipi = _fval(icms_tot, "vIPI")
            v_ipi_devol = _fval(icms_tot, "vIPIDevol")
            v_pis = _fval(icms_tot, "vPIS")
            v_cofins = _fval(icms_tot, "vCOFINS")
            v_outro = _fval(icms_tot, "vOutro")
            v_nf = _fval(icms_tot, "vNF")
            v_tot_trib = _fval(icms_tot, "vTotTrib")

            # Grupo X – Transporte
            transp = _find(inf_nfe, "transp")
            transp_mod_frete = _text(transp, "modFrete") if transp is not None else None
            transporta = _find(transp, "transporta") if transp is not None else None
            transp_cnpj = _text(transporta, "CNPJ") if transporta is not None else None
            transp_cpf = _text(transporta, "CPF") if transporta is not None else None
            transp_x_nome = (
                _text(transporta, "xNome") if transporta is not None else None
            )
            transp_ie = _text(transporta, "IE") if transporta is not None else None
            transp_x_ender = (
                _text(transporta, "xEnder") if transporta is not None else None
            )
            transp_x_mun = _text(transporta, "xMun") if transporta is not None else None
            transp_uf = _text(transporta, "UF") if transporta is not None else None
            ret_transp = _find(transp, "retTransp") if transp is not None else None
            transp_v_serv = (
                _fval(ret_transp, "vServ") if ret_transp is not None else 0.0
            )
            transp_v_bc_ret = (
                _fval(ret_transp, "vBCRet") if ret_transp is not None else 0.0
            )
            transp_p_icms_ret = (
                _fval(ret_transp, "pICMSRet") if ret_transp is not None else 0.0
            )
            transp_v_icms_ret = (
                _fval(ret_transp, "vICMSRet") if ret_transp is not None else 0.0
            )
            transp_cfop = _text(ret_transp, "CFOP") if ret_transp is not None else None
            transp_c_mun_fg = (
                _text(ret_transp, "cMunFG") if ret_transp is not None else None
            )
            veic_transp = _find(transp, "veicTransp") if transp is not None else None
            transp_placa = (
                _text(veic_transp, "placa") if veic_transp is not None else None
            )
            transp_uf_veic = (
                _text(veic_transp, "UF") if veic_transp is not None else None
            )
            transp_rntc = (
                _text(veic_transp, "RNTC") if veic_transp is not None else None
            )

            # Grupo YA – Pagamento
            pag_el = _find(inf_nfe, "pag")
            pag_v_troco = _fval(pag_el, "vTroco") if pag_el is not None else 0.0

            # Grupo YB – Intermediador
            inf_intermed = _find(inf_nfe, "infIntermed")
            intermed_cnpj = (
                _text(inf_intermed, "CNPJ") if inf_intermed is not None else None
            )
            intermed_id_cad_int_tran = (
                _text(inf_intermed, "idCadIntTran")
                if inf_intermed is not None
                else None
            )

            # Grupo Y – Cobrança
            cobr = _find(inf_nfe, "cobr")
            fat = _find(cobr, "fat") if cobr is not None else None
            fat_n_fat = _text(fat, "nFat") if fat is not None else None
            fat_v_orig = _fval(fat, "vOrig") if fat is not None else 0.0
            fat_v_desc = _fval(fat, "vDesc") if fat is not None else 0.0
            fat_v_liq = _fval(fat, "vLiq") if fat is not None else 0.0

            # Grupo Z – Informações adicionais
            inf_adic = _find(inf_nfe, "infAdic")
            if inf_adic is not None:
                inf_cpl = _text(inf_adic, "infCpl") or None
                inf_ad_fisco = _text(inf_adic, "infAdFisco") or None
            else:
                inf_cpl = None
                inf_ad_fisco = None

            # # Se tags obrigatórias não existirem, aborta (evita gravação parcial inválida)
            # required_str_fields = {
            #     "versao": versao,
            #     "ch_nfe": ch_nfe,
            #     "c_uf": c_uf,
            #     "nat_op": nat_op,
            #     "mod": mod,
            #     "serie": serie,
            #     "n_nf": n_nf,
            #     "dh_emi": dh_emi,
            #     "tp_nf": tp_nf,
            #     "id_dest": id_dest,
            #     "tp_amb": tp_amb or dfe_doc.tp_amb,
            #     "emit_x_nome": emit_x_nome,
            #     "emit_ender_x_lgr": emit_ender_x_lgr,
            #     "emit_ender_nro": emit_ender_nro,
            #     "emit_ender_xBairro": emit_ender_xBairro,
            #     "emit_ender_cMun": emit_ender_cMun,
            #     "emit_ender_xMun": emit_ender_xMun,
            #     "emit_ender_UF": emit_ender_UF,
            #     "emit_ender_CEP": emit_ender_CEP,
            #     "emit_ender_cPais": emit_ender_cPais,
            #     "emit_ender_xPais": emit_ender_xPais,
            #     "emit_ie": emit_ie,
            #     "emit_crt": emit_crt,
            # }
            # missing = [k for k, v in required_str_fields.items() if not v]
            # if missing:
            #     _logger.warning(
            #         f"DFe {dfe_doc.nsu}: faltando campos obrigatórios no XML: {', '.join(missing)}"
            #     )
            #     return None

            vals = {
                # Vínculos
                "company_id": dfe_doc.company_id.id,
                "dfe_document_id": dfe_doc.id,
                "tp_amb": dfe_doc.tp_amb,
                # Identificação
                "versao": versao,
                "ch_nfe": ch_nfe,
                "c_uf": c_uf,
                "nat_op": nat_op,
                "mod": mod,
                "serie": serie,
                "n_nf": n_nf,
                "dh_emi": dh_emi,
                "dh_sai_ent": dh_sai_ent,
                "tp_nf": tp_nf,
                "id_dest": id_dest,
                "c_mun_fg": c_mun_fg,
                "tp_imp": tp_imp,
                "tp_emis": tp_emis,
                "fin_nfe": fin_nfe,
                "ind_final": ind_final,
                "ind_pres": ind_pres,
                "ind_intermed": ind_intermed,
                "proc_emi": proc_emi,
                # Emitente
                "emit_cnpj": emit_cnpj,
                "emit_cpf": emit_cpf,
                "emit_x_nome": emit_x_nome,
                "emit_x_fant": emit_x_fant,
                "emit_ender_x_lgr": emit_ender_x_lgr,
                "emit_ender_nro": emit_ender_nro,
                "emit_ender_xCpl": emit_ender_xCpl,
                "emit_ender_xBairro": emit_ender_xBairro,
                "emit_ender_cMun": emit_ender_cMun,
                "emit_ender_xMun": emit_ender_xMun,
                "emit_ender_UF": emit_ender_UF,
                "emit_ender_CEP": emit_ender_CEP,
                "emit_ender_cPais": emit_ender_cPais,
                "emit_ender_xPais": emit_ender_xPais,
                "emit_ender_fone": emit_ender_fone,
                "emit_ie": emit_ie,
                "emit_iest": emit_iest,
                "emit_im": emit_im,
                "emit_cnae": emit_cnae,
                "emit_crt": emit_crt,
                # Destinatário
                "dest_cnpj": dest_cnpj,
                "dest_cpf": dest_cpf,
                "dest_id_estrangeiro": dest_id_estrangeiro,
                "dest_x_nome": dest_x_nome,
                "dest_ind_ie": dest_ind_ie,
                "dest_ie": dest_ie,
                "dest_isuf": dest_isuf,
                "dest_im": dest_im,
                "dest_ender_x_lgr": dest_ender_x_lgr,
                "dest_ender_nro": dest_ender_nro,
                "dest_ender_xCpl": dest_ender_xCpl,
                "dest_ender_xBairro": dest_ender_xBairro,
                "dest_ender_cMun": dest_ender_cMun,
                "dest_ender_xMun": dest_ender_xMun,
                "dest_ender_UF": dest_ender_UF,
                "dest_ender_CEP": dest_ender_CEP,
                "dest_ender_cPais": dest_ender_cPais,
                "dest_ender_xPais": dest_ender_xPais,
                "dest_ender_fone": dest_ender_fone,
                "dest_email": dest_x_email,
                # Totais
                "v_bc": v_bc,
                "v_icms": v_icms,
                "v_icms_deson": v_icms_deson,
                "v_fcp_uf_dest": v_fcp_uf_dest,
                "v_icms_uf_dest": v_icms_uf_dest,
                "v_icms_uf_remet": v_icms_uf_remet,
                "v_fcp": v_fcp,
                "v_bc_st": v_bc_st,
                "v_st": v_st,
                "v_fcp_st": v_fcp_st,
                "v_fcp_st_ret": v_fcp_st_ret,
                "v_prod": v_prod,
                "v_frete": v_frete,
                "v_seg": v_seg,
                "v_desc": v_desc,
                "v_ii": v_ii,
                "v_ipi": v_ipi,
                "v_ipi_devol": v_ipi_devol,
                "v_pis": v_pis,
                "v_cofins": v_cofins,
                "v_outro": v_outro,
                "v_nf": v_nf,
                "v_tot_trib": v_tot_trib,
                # Transporte
                "transp_mod_frete": transp_mod_frete,
                "transp_cnpj": transp_cnpj,
                "transp_cpf": transp_cpf,
                "transp_x_nome": transp_x_nome,
                "transp_ie": transp_ie,
                "transp_x_ender": transp_x_ender,
                "transp_x_mun": transp_x_mun,
                "transp_uf": transp_uf,
                "transp_v_serv": transp_v_serv,
                "transp_v_bc_ret": transp_v_bc_ret,
                "transp_p_icms_ret": transp_p_icms_ret,
                "transp_v_icms_ret": transp_v_icms_ret,
                "transp_cfop": transp_cfop,
                "transp_c_mun_fg": transp_c_mun_fg,
                "transp_placa": transp_placa,
                "transp_uf_veic": transp_uf_veic,
                "transp_rntc": transp_rntc,
                # Pagamento
                "pag_v_troco": pag_v_troco,
                # Intermediador
                "intermed_cnpj": intermed_cnpj,
                "intermed_id_cad_int_tran": intermed_id_cad_int_tran,
                # Cobrança
                "fat_n_fat": fat_n_fat,
                "fat_v_orig": fat_v_orig,
                "fat_v_desc": fat_v_desc,
                "fat_v_liq": fat_v_liq,
                # Informações adicionais
                "inf_cpl": inf_cpl,
                "inf_ad_fisco": inf_ad_fisco,
            }

            record = self.create(vals)
            _logger.info(
                f"procNFe criado: id={record.id} chNFe={ch_nfe} NSU={dfe_doc.nsu}"
            )

            # Vincular resNFe correspondente pela chave de acesso
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
                    res_nfe.proc_nfe_id = record.id

                proc_evento_nfe_list = self.env[
                    "l10n_br_dfe_monitor.proc_evento_nfe"
                ].search(
                    [
                        ("ch_nfe", "=", ch_nfe),
                        ("company_id", "=", dfe_doc.company_id.id),
                        ("tp_amb", "=", dfe_doc.tp_amb),
                    ],
                )
                for proc_evento_nfe in proc_evento_nfe_list:
                    proc_evento_nfe.proc_nfe_id = record.id

            # Criar detalhamentos de pagamento
            if pag_el is not None:
                NS_find = f"{{{NS}}}"
                Pag = self.env["l10n_br_dfe_monitor.proc_nfe_pag"]
                for det_pag in pag_el.findall(f"{NS_find}detPag"):
                    card_el = det_pag.find(f"{NS_find}card")
                    Pag.create(
                        {
                            "proc_nfe_id": record.id,
                            "ind_pag": _text(det_pag, "indPag"),
                            "t_pag": _text(det_pag, "tPag"),
                            "v_pag": _fval(det_pag, "vPag"),
                            "tp_integra": (
                                _text(card_el, "tpIntegra")
                                if card_el is not None
                                else False
                            ),
                            "card_cnpj": (
                                _text(card_el, "CNPJ") if card_el is not None else False
                            ),
                            "t_band": (
                                _text(card_el, "tBand")
                                if card_el is not None
                                else False
                            ),
                            "c_aut": (
                                _text(card_el, "cAut") if card_el is not None else False
                            ),
                        }
                    )

            # Criar parcelas de cobrança
            if cobr is not None:
                NS_find = f"{{{NS}}}"
                Dup = self.env["l10n_br_dfe_monitor.proc_nfe_dup"]
                for dup_el in cobr.findall(f"{NS_find}dup"):
                    n_dup = _text(dup_el, "nDup")
                    d_venc_str = _text(dup_el, "dVenc")
                    v_dup = _fval(dup_el, "vDup")
                    Dup.create(
                        {
                            "proc_nfe_id": record.id,
                            "n_dup": n_dup,
                            "d_venc": d_venc_str or False,
                            "v_dup": v_dup,
                        }
                    )

            # Criar itens a partir dos elementos <det>
            Item = self.env["l10n_br_dfe_monitor.proc_nfe_item"]
            for det_el in nfe.findall(f"{{{NS}}}infNFe/{{{NS}}}det"):
                Item._create_from_det(record, det_el)

            return record

        except Exception as e:
            _logger.error(
                f"Erro ao criar procNFe para DFe NSU={dfe_doc.nsu}: {e}",
                exc_info=True,
            )
            raise
