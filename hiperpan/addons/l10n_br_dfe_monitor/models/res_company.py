"""
Extensão de res.company para DFe Monitor
"""
import random
from datetime import datetime, time, timedelta

from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    dfe_last_nsu = fields.Char(
        string="Último NSU DFe",
        help="Último NSU recebido na consulta NFeDistribuicaoDFe. Atualizado automaticamente.",
    )
    dfe_max_nsu = fields.Char(
        string="Maior NSU disponível",
        help="Maior NSU disponível no Ambiente Nacional para esta empresa.",
    )

    dfe_receiving_schedule_ids = fields.One2many(
        "l10n_br_dfe_monitor.receiving_schedule",
        "company_id",
        string="Janelas de Recebimento de Mercadorias",
        help=(
            "Dias e horários em que a empresa costuma receber mercadorias. "
            "Usado para sugerir a Data de Chegada ao escriturar uma NF-e."
        ),
    )

    def _get_next_receiving_datetime(self, anchor_datetime, max_days_ahead=60):
        """Pick a random, plausible arrival datetime on the next day the store
        has a configured receiving window, strictly after ``anchor_datetime``'s
        date.

        - Searches day by day, starting the day after ``anchor_datetime``.
        - On the first matching weekday that has one or more receiving
          schedule lines, a line is picked at random, then a random time
          within [hour_from, hour_to) is generated, rounded down to the
          nearest 5-minute mark with zero seconds.
        - Returns ``False`` if no schedule is configured at all (nothing to
          base a suggestion on) or none is found within ``max_days_ahead``.
        """
        self.ensure_one()
        if not anchor_datetime:
            return False

        schedules = self.dfe_receiving_schedule_ids
        if not schedules:
            return False

        by_weekday = {}
        for line in schedules:
            by_weekday.setdefault(line.weekday, []).append(line)

        anchor_date = anchor_datetime.date()
        for offset in range(1, max_days_ahead + 1):
            candidate_date = anchor_date + timedelta(days=offset)
            # Python's Monday=0 matches this model's weekday selection (0=Mon).
            weekday_str = str(candidate_date.weekday())
            day_lines = by_weekday.get(weekday_str)
            if not day_lines:
                continue

            chosen_line = random.choice(day_lines)
            return self._random_rounded_datetime(candidate_date, chosen_line)

        return False

    @staticmethod
    def _random_rounded_datetime(target_date, schedule_line):
        """Random datetime on ``target_date`` within the line's hour window,
        with seconds zeroed and minutes rounded down to a multiple of 5."""
        total_minutes_from = round(schedule_line.hour_from * 60)
        total_minutes_to = round(schedule_line.hour_to * 60)
        # Keep the window valid after rounding down to a 5-minute slot.
        last_slot = ((total_minutes_to - 1) // 5) * 5
        first_slot = -(-total_minutes_from // 5) * 5  # ceil to multiple of 5
        if first_slot > last_slot:
            first_slot = last_slot

        chosen_minute_of_day = random.randrange(first_slot, last_slot + 1, 5)
        hour, minute = divmod(chosen_minute_of_day, 60)
        return datetime.combine(target_date, time(hour=hour, minute=minute, second=0))
