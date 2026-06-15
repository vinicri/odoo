from odoo import api, fields, models


class DfeNfeEscrit(models.Model):
    _name = "l10n_br_dfe_monitor.dfe_nfe_escrit"
    _description = "Escrituração de NF-e"

    proc_nfe_id = fields.Many2one(
        "l10n_br_dfe_monitor.proc_nfe",
        string="NF-e Processada",
        ondelete="set null",
        readonly=True,
        index=True,
    )

    # save this in case the proc_nfe_id is deleted
    ch_nfe = fields.Char(
        string="Chave de Acesso",
        size=44,
        compute="_compute_ch_nfe",
        required=True,
        store=True,
        readonly=True,
        index=True,
    )

    @api.depends("proc_nfe_id.ch_nfe")
    def _compute_ch_nfe(self):
        for rec in self:
            rec.ch_nfe = rec.proc_nfe_id.ch_nfe

    partner_id = fields.Many2one(
        "res.partner",
        string="Parceiro",
        required=True,
        ondelete="cascade",
        compute="_compute_partner_id",
        store=True,
        readonly=False,
        index=True,
    )

    @api.depends("proc_nfe_id.emit_cnpj", "proc_nfe_id.emit_cpf")
    def _compute_partner_id(self):
        for rec in self:
            vat = rec.proc_nfe_id.emit_cnpj or rec.proc_nfe_id.emit_cpf
            if vat:
                partner = self.env["res.partner"].search([("vat", "=", vat)], limit=1)
                rec.partner_id = partner
            else:
                rec.partner_id = False

    _sql_constraints = [
        (
            "proc_nfe_id_unique",
            "UNIQUE(proc_nfe_id)",
            "Cada NF-e processada só pode ter uma escrituração.",
        )
    ]
