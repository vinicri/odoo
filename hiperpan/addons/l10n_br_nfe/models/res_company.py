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

    # IBPT Configuration
    ibpt_token = fields.Char(
        string="Token IBPT",
        help="Token de acesso à API do IBPT (De Olho no Imposto). "
        "Obtenha em: https://deolhonoimposto.ibpt.org.br/",
    )

    ibpt_update_days = fields.Integer(
        string="Dias para Atualização IBPT",
        default=180,
        help="Número de dias para considerar os dados do IBPT desatualizados.",
    )

    tech_contact_id = fields.Many2one(
        comodel_name="l10n_br_nfe.nfe.tech.contact",
        string="Responsável Técnico",
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
