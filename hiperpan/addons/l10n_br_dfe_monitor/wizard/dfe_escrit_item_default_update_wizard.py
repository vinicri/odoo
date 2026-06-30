"""
Wizard to confirm updating an existing escrituração-item defaults record when a
newly entered item differs from the stored default. Shows current vs. new values
for each tracked field that changed.
"""

import json

from odoo import fields, models, _


class DfeEscritItemDefaultUpdateWizard(models.TransientModel):
    _name = "l10n_br_dfe_monitor.escrit_item_default_update_wizard"
    _description = "Atualizar Item de Escrituração Padrão"

    defaults_id = fields.Many2one(
        "l10n_br_dfe_monitor.dfe_nfe_escrit_item_defaults",
        string="Item Padrão",
        required=True,
        readonly=True,
    )
    # JSON-encoded {field_name: new_value} for the values to apply on confirm.
    new_vals_json = fields.Char(readonly=True)
    # Human-readable "current vs new" summary rendered in the wizard.
    diff_html = fields.Html(string="Alterações", readonly=True, sanitize=False)

    def open_for(self, defaults, new_vals, differences):
        """Build and return the act_window action that opens this wizard.

        :param defaults: existing dfe_nfe_escrit_item_defaults record
        :param new_vals: full values dict that would be written
        :param differences: list of (item_field, defaults_field) tuples that changed
        """
        rows = []
        for _item_field, def_field in differences:
            field = self.env["l10n_br_dfe_monitor.dfe_nfe_escrit_item_defaults"]._fields[
                def_field
            ]
            label = field.string
            current_display = self._format_value(defaults, def_field)
            new_display = self._format_value_from_vals(def_field, new_vals.get(def_field))
            rows.append(
                "<tr>"
                "<td style='padding:2px 8px;font-weight:bold'>%s</td>"
                "<td style='padding:2px 8px;color:#b94a48'>%s</td>"
                "<td style='padding:2px 8px'>&rarr;</td>"
                "<td style='padding:2px 8px;color:#468847'>%s</td>"
                "</tr>" % (label, current_display or "—", new_display or "—")
            )
        diff_html = (
            "<table style='border-collapse:collapse'>"
            "<thead><tr>"
            "<th style='padding:2px 8px;text-align:left'>%s</th>"
            "<th style='padding:2px 8px;text-align:left'>%s</th>"
            "<th></th>"
            "<th style='padding:2px 8px;text-align:left'>%s</th>"
            "</tr></thead><tbody>%s</tbody></table>"
            % (_("Campo"), _("Atual"), _("Novo"), "".join(rows))
        )

        # Only persist the changed fields so confirming touches nothing else.
        changed_vals = {
            def_field: new_vals.get(def_field) for _i, def_field in differences
        }

        wizard = self.create(
            {
                "defaults_id": defaults.id,
                "new_vals_json": json.dumps(changed_vals),
                "diff_html": diff_html,
            }
        )
        return {
            "type": "ir.actions.act_window",
            "name": _("Atualizar Item Padrão?"),
            "res_model": self._name,
            "res_id": wizard.id,
            "view_mode": "form",
            "target": "new",
        }

    def _format_value(self, record, field_name):
        field = record._fields[field_name]
        value = record[field_name]
        if field.type == "many2one":
            return value.display_name if value else ""
        if field.type == "boolean":
            return _("Sim") if value else _("Não")
        return value or ""

    def _format_value_from_vals(self, field_name, raw_value):
        field = self.env[
            "l10n_br_dfe_monitor.dfe_nfe_escrit_item_defaults"
        ]._fields[field_name]
        if field.type == "many2one":
            if raw_value:
                return self.env[field.comodel_name].browse(raw_value).display_name
            return ""
        if field.type == "boolean":
            return _("Sim") if raw_value else _("Não")
        return raw_value or ""

    def action_confirm(self):
        self.ensure_one()
        self.defaults_id.write(json.loads(self.new_vals_json or "{}"))
        return {"type": "ir.actions.act_window_close"}
