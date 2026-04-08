"""
Brazilian DFe Monitor - Detalhamento de Pagamento da NF-e (pag/detPag)
"""

from odoo import fields, models


class DfeProcNfePag(models.Model):
    _name = "l10n_br_dfe_monitor.proc_nfe_pag"
    _description = "Detalhamento de Pagamento da NF-e (pag/detPag)"
    _order = "proc_nfe_id, id"
    _rec_name = "t_pag"

    proc_nfe_id = fields.Many2one(
        "l10n_br_dfe_monitor.proc_nfe",
        string="NF-e",
        required=True,
        ondelete="cascade",
        index=True,
    )

    # YA01b – Indicador da Forma de Pagamento (1)
    ind_pag = fields.Selection(
        [("0", "À Vista"), ("1", "À Prazo")],
        string="Indicador Pagamento",
        readonly=True,
    )
    # YA02 – Meio de Pagamento (2)
    t_pag = fields.Selection(
        [
            ("01", "Dinheiro"),
            ("02", "Cheque"),
            ("03", "Cartão de Crédito"),
            ("04", "Cartão de Débito"),
            ("05", "Crédito Loja"),
            ("10", "Vale Alimentação"),
            ("11", "Vale Refeição"),
            ("12", "Vale Presente"),
            ("13", "Vale Combustível"),
            ("15", "Boleto Bancário"),
            ("16", "Depósito Bancário"),
            ("17", "PIX"),
            ("18", "Transferência Bancária / Carteira Digital"),
            ("19", "Fidelidade / Cashback / Crédito Virtual"),
            ("90", "Sem Pagamento"),
            ("99", "Outros"),
        ],
        string="Meio de Pagamento",
        readonly=True,
    )
    # YA03 – Valor do Pagamento (13v2)
    v_pag = fields.Float(string="Valor Pagamento", digits=(13, 2), readonly=True)
    # YA04a – Tipo de Integração do pagamento (1)
    tp_integra = fields.Selection(
        [("1", "Integrado (TEF/e-commerce)"), ("2", "Não Integrado (POS)")],
        string="Tipo Integração",
        readonly=True,
    )
    # YA05 – CNPJ da instituição de pagamento (14)
    card_cnpj = fields.Char(string="CNPJ Operadora", size=14, readonly=True)
    # YA06 – Bandeira do cartão (2)
    t_band = fields.Selection(
        [
            ("01", "Visa"),
            ("02", "Mastercard"),
            ("03", "American Express"),
            ("04", "Sorocred"),
            ("05", "Diners Club"),
            ("06", "Elo"),
            ("07", "Hipercard"),
            ("08", "Aura"),
            ("09", "Cabal"),
            ("99", "Outros"),
        ],
        string="Bandeira",
        readonly=True,
    )
    # YA07 – Número de autorização (1-20)
    c_aut = fields.Char(string="Nº Autorização", size=20, readonly=True)
