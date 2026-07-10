"""
Janelas de recebimento de mercadorias por empresa: dia da semana + horário em
que fornecedores costumam entregar. Usado para pré-popular a Data de Chegada
da escrituração de NF-e com um horário plausível.
"""

from odoo import api, fields, models
from odoo.exceptions import ValidationError


class DfeReceivingSchedule(models.Model):
    _name = "l10n_br_dfe_monitor.receiving_schedule"
    _description = "Janela de Recebimento de Mercadorias"
    _order = "weekday, hour_from"

    company_id = fields.Many2one(
        "res.company",
        string="Empresa",
        required=True,
        default=lambda self: self.env.company,
        ondelete="cascade",
        index=True,
    )

    weekday = fields.Selection(
        [
            ("0", "Segunda-feira"),
            ("1", "Terça-feira"),
            ("2", "Quarta-feira"),
            ("3", "Quinta-feira"),
            ("4", "Sexta-feira"),
            ("5", "Sábado"),
            ("6", "Domingo"),
        ],
        string="Dia da Semana",
        required=True,
    )

    hour_from = fields.Float(
        string="Hora Inicial",
        required=True,
        help="Horário inicial de recebimento, em horas decimais (ex: 8.5 = 08:30).",
    )
    hour_to = fields.Float(
        string="Hora Final",
        required=True,
        help="Horário final de recebimento, em horas decimais (ex: 17.5 = 17:30).",
    )

    @api.constrains("hour_from", "hour_to")
    def _check_hours(self):
        for rec in self:
            if not (0 <= rec.hour_from < 24) or not (0 < rec.hour_to <= 24):
                raise ValidationError(
                    "O horário de recebimento deve estar entre 00:00 e 24:00."
                )
            if rec.hour_from >= rec.hour_to:
                raise ValidationError(
                    "A hora inicial deve ser anterior à hora final."
                )
