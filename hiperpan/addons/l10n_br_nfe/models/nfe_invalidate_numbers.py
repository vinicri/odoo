from odoo import models, fields, api, _

class NfeInvalidateNumbers(models.Model):
    _name = 'l10n_br_nfe.nfe.invalidate.numbers'
    _description = 'Invalidate number in fiscal document series'

    name = fields.Char(string="Name", compute="_compute_name", store=True, index=True)

    company_id = fields.Many2one(
        comodel_name="res.company", 
        default=lambda self: self.env.company.id,
        string="Company", 
        required=True,
    )

    series_id = fields.Many2one(
        comodel_name="l10n_br_nfe.nfe.series", 
        string="Series", 
        domain="[('company_id', '=', company_id)]",
        required=True,
    )

    document_model = fields.Selection(
        related='series_id.document_model',
        string="Modelo do Documento Fiscal",
        readonly=True,
    )

    reason = fields.Char(string="Reason", required=True)

    number_start = fields.Integer(string="Number Start", required=True)
    number_end = fields.Integer(string="Number End", required=True)

    active = fields.Boolean(string="Active", default=True)

    _sql_constraints = [
        ('nfe_invalidate_numbers_unique', 'unique(company_id, series_id, document_model, number_start, number_end, active)', 'Já existe um número inválido para o modelo de documento selecionado.')
    ]

    @api.depends("document_model", "series_id", "number_start", "number_end")
    def _compute_name(self):
        for record in self:
            if not record.document_model or not record.series_id or not record.number_start or not record.number_end:
                record.name = ""
            else:
              record.name = "Modelo {model} / Série {serie}: {start} - {end}".format(
                  model=record.document_model,
                  serie=record.series_id.series,
                  start=record.number_start,
                  end=record.number_end,
              )