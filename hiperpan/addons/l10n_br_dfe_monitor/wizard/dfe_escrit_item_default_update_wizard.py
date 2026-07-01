"""
Wizard shown while saving an escrituração item (in its modal) when the item
differs from its stored item-defaults record. It shows the current vs. new
values and lets the user confirm updating the default.

Because the item is still unsaved when its modal is saved, the wizard does not
reference the item record: it stores the target defaults record and the new
tracked values directly, so confirming can write them without the item.
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
    # JSON of {defaults_field: value} to write when the user confirms.
    new_vals_json = fields.Char(readonly=True)
    diff_html = fields.Html(string="Alterações", readonly=True, sanitize=False)

    def create_for_defaults(self, defaults, new_vals):
        """Create the wizard record for a differing default.

        :param defaults: the existing dfe_nfe_escrit_item_defaults record
        :param new_vals: full defaults-record values dict from the item
        :return: the created wizard record
        """
        item_model = self.env["l10n_br_dfe_monitor.dfe_nfe_escrit_item"]
        tracked = {
            def_field: new_vals.get(def_field)
            for _item_field, def_field in item_model._DEFAULT_TRACKED_FIELDS
        }
        return self.create(
            {
                "defaults_id": defaults.id,
                "new_vals_json": json.dumps(tracked),
                "diff_html": self._build_diff_html(defaults, tracked),
            }
        )

    def _build_diff_html(self, defaults, tracked):
        rows = []
        item_model = self.env["l10n_br_dfe_monitor.dfe_nfe_escrit_item"]
        for _item_field, def_field in item_model._DEFAULT_TRACKED_FIELDS:
            new_value = tracked.get(def_field)
            if not item_model._defaults_field_differs(defaults, def_field, new_value):
                continue
            label = defaults._fields[def_field].string
            current_display = self._format_current(defaults, def_field)
            new_display = self._format_new(def_field, new_value)
            rows.append(
                "<tr>"
                "<td style='padding:2px 8px;font-weight:bold'>%s</td>"
                "<td style='padding:2px 8px;color:#b94a48'>%s</td>"
                "<td style='padding:2px 8px'>&rarr;</td>"
                "<td style='padding:2px 8px;color:#468847'>%s</td>"
                "</tr>" % (label, current_display or "—", new_display or "—")
            )
        return (
            "<table style='border-collapse:collapse'>"
            "<thead><tr>"
            "<th style='padding:2px 8px;text-align:left'>%s</th>"
            "<th style='padding:2px 8px;text-align:left'>%s</th>"
            "<th></th>"
            "<th style='padding:2px 8px;text-align:left'>%s</th>"
            "</tr></thead><tbody>%s</tbody></table>"
            % (_("Campo"), _("Atual"), _("Novo"), "".join(rows))
        )

    def _format_current(self, defaults, field_name):
        field = defaults._fields[field_name]
        value = defaults[field_name]
        if field.type == "many2one":
            return value.display_name if value else ""
        if field.type == "boolean":
            return _("Sim") if value else _("Não")
        return value or ""

    def _format_new(self, field_name, raw_value):
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
        # No action returned: the button carries close="1", so the dialog service
        # closes this wizard dialog only (returning act_window_close here would
        # instead tear down the underlying escrituração action-dialog).
        return False
