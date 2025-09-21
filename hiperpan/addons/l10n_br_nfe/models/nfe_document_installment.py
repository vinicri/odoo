from odoo import models, fields, api


class NFeDocumentInstallment(models.Model):
    _name = "l10n_br_nfe.nfe.document.installment"
    _description = "Parcelas da NF-e"
    _order = "due_date asc"

    nfe_id = fields.Many2one(
        comodel_name="l10n_br_nfe.nfe.document",
        string="NF-e",
        required=True,
        ondelete="cascade",
    )

    installment_number = fields.Char(string="Número da Parcela", required=True, size=3)
    # Obrigatória informação do número de parcelas com 3 algarismos, sequenciais e consecutivos. Ex.: “001”,”002”,”003”,... [105, 231]

    due_date = fields.Date(string="Data de Vencimento", required=True)
    # Formato: “AAAA-MM-DD”. Obrigatória a informação da data de vencimento na ordem crescente das datas. [105, 106]

    value = fields.Float(string="Valor da Parcela", required=True, digits=(13, 2))
    # Valor da Parcela.
