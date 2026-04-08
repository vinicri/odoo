"""
Brazilian DFe Monitor - Parcelas de Cobrança da NF-e (cobr/dup)
"""

from odoo import fields, models


class DfeProcNfeDup(models.Model):
    _name = "l10n_br_dfe_monitor.proc_nfe_dup"
    _description = "Parcela de Cobrança da NF-e (cobr/dup)"
    _order = "proc_nfe_id, n_dup"
    _rec_name = "n_dup"

    proc_nfe_id = fields.Many2one(
        "l10n_br_dfe_monitor.proc_nfe",
        string="NF-e",
        required=True,
        ondelete="cascade",
        index=True,
    )

    # Y08 – Número da Parcela (1-60)
    n_dup = fields.Char(string="Nº Parcela", size=60, readonly=True)
    # Y09 – Data de Vencimento
    d_venc = fields.Date(string="Vencimento", readonly=True)
    # Y10 – Valor da Parcela (13v2)
    v_dup = fields.Float(string="Valor Parcela", digits=(13, 2), readonly=True)
