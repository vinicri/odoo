"""
Wizard para consulta de DFes
"""
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class DfeQueryWizard(models.TransientModel):
    _name = "l10n_br_dfe_monitor.query.wizard"
    _description = "Consultar DFe - NFeDistribuicaoDFe"

    query_type = fields.Selection(
        [
            ("distNSU", "Buscar novos DFes (a partir do último NSU)"),
            ("consNSU", "Consultar DFe por NSU específico"),
            ("consChNFe", "Consultar NF-e por Chave de Acesso"),
        ],
        string="Tipo de Consulta",
        required=True,
        default="distNSU",
    )
    nsu = fields.Char(string="NSU", help="Número Sequencial Único (para consulta por NSU)")
    ch_nfe = fields.Char(string="Chave de Acesso", size=44, help="44 dígitos da chave de acesso da NF-e")
    result_message = fields.Text(string="Resultado", readonly=True)

    @api.onchange("query_type")
    def _onchange_query_type(self):
        self.nsu = False
        self.ch_nfe = False

    def action_consult(self):
        self.ensure_one()

        if self.query_type == "consNSU" and not self.nsu:
            raise UserError(_("Informe o NSU para consulta por NSU."))
        if self.query_type == "consChNFe" and not self.ch_nfe:
            raise UserError(_("Informe a Chave de Acesso para consulta por chave."))

        DfeDocument = self.env["l10n_br_dfe_monitor.document"]

        result = DfeDocument.consult_dist_dfe(
            query_type=self.query_type,
            nsu=self.nsu,
            ch_nfe=self.ch_nfe,
        )

        new_count = result.get("new_count", 0)
        ult_nsu = result.get("ult_nsu", "-")
        max_nsu = result.get("max_nsu", "-")
        x_motivo = result.get("x_motivo", "")

        # Atualizar NSUs na empresa
        company = self.env.company
        company.write({
            "dfe_last_nsu": ult_nsu,
            "dfe_max_nsu": max_nsu,
        })

        msg = _(
            "Consulta realizada com sucesso!\n\n"
            "Status: %(x_motivo)s\n"
            "Último NSU pesquisado: %(ult_nsu)s\n"
            "Maior NSU disponível: %(max_nsu)s\n"
            "Novos documentos recebidos: %(new_count)s"
        ) % {
            "x_motivo": x_motivo,
            "ult_nsu": ult_nsu,
            "max_nsu": max_nsu,
            "new_count": new_count,
        }
        self.result_message = msg

        if result.get("new_doc_ids"):
            return {
                "type": "ir.actions.act_window",
                "name": _("DFes Recebidos"),
                "res_model": "l10n_br_dfe_monitor.document",
                "view_mode": "list,form",
                "domain": [("id", "in", result["new_doc_ids"])],
                "target": "current",
            }

        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
        }
