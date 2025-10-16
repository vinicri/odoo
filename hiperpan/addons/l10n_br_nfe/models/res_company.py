from odoo import models, fields, api
import pytz
from datetime import datetime

ENV_EMISSION = [("0", "Produção"), ("1", "Homologação")]


class Company(models.Model):
    _name = "res.company"
    _inherit = ["res.company"]

    fiscal_document_emission_env = fields.Selection(
        ENV_EMISSION,
        string="Ambiente de Emissão de Documentos Fiscais",
        required=True,
        tracking=True,
        default="1",
    )

    @api.model
    def _get_timezone_list(self):
        """
        Retorna lista de timezones com o offset UTC atual.
        Exemplo: America/Sao_Paulo (UTC-3:00)
        """
        timezones = []
        now = datetime.now(pytz.UTC)

        for tz_name in pytz.all_timezones:
            try:
                tz = pytz.timezone(tz_name)
                # Obtém o offset atual (considera horário de verão)
                offset = now.astimezone(tz).strftime("%z")
                # Formata o offset para ficar legível: -0300 -> -03:00
                offset_formatted = f"{offset[:3]}:{offset[3:]}"

                # Cria label com nome e offset
                label = f"{tz_name} (UTC{offset_formatted})"
                timezones.append((tz_name, label))
            except:
                # Caso algum timezone seja problemático, adiciona sem offset
                timezones.append((tz_name, tz_name))

        return timezones

    time_zone = fields.Selection(
        selection=_get_timezone_list,
        string="Time Zone",
        required=True,
        default="America/Sao_Paulo",
    )
