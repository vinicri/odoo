"""
Brazilian DFe Monitor - Wizard para Operação não Realizada (210240)
"""

from odoo import fields, models, _
from odoo.exceptions import UserError
from ..utils.send_manifestacao import send_manifestacao


class DfeManifestacaoNaoRealizadaWizard(models.TransientModel):
    _name = "l10n_br_dfe_monitor.manifestacao_nao_realizada_wizard"
    _description = "Justificativa — Operação não Realizada"

    res_nfe_id = fields.Many2one(
        "l10n_br_dfe_monitor.res_nfe",
        string="Resumo NF-e",
        required=True,
        readonly=True,
    )
    x_just = fields.Char(
        string="Justificativa",
        required=True,
        size=255,
        help="Mínimo 15 caracteres. Informe o motivo pelo qual a operação não foi realizada.",
    )

    def action_confirmar(self):
        self.ensure_one()
        if len(self.x_just.strip()) < 15:
            raise UserError(_("A justificativa deve ter no mínimo 15 caracteres."))
        rec = self.res_nfe_id
        send_manifestacao(
            company=rec.company_id,
            ch_nfe=rec.ch_nfe,
            tp_evento="210240",
            tp_amb=rec.tp_amb,
            x_just=self.x_just,
        )
        rec.manifestacao = "nao_realizada"
        return {"type": "ir.actions.act_window_close"}
