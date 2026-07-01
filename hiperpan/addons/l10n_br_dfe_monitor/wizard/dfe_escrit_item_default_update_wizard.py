"""
Wizard shown after saving an escrituração when an item differs from its stored
item-defaults record. It shows the current vs. new values for that single item
and lets the user confirm updating the default. One wizard is opened per
conflicting item.
"""

from odoo import fields, models, _


class DfeEscritItemDefaultUpdateWizard(models.TransientModel):
    _name = "l10n_br_dfe_monitor.escrit_item_default_update_wizard"
    _description = "Atualizar Item de Escrituração Padrão"

    item_id = fields.Many2one(
        "l10n_br_dfe_monitor.dfe_nfe_escrit_item",
        string="Item",
        required=True,
        readonly=True,
    )
    defaults_id = fields.Many2one(
        "l10n_br_dfe_monitor.dfe_nfe_escrit_item_defaults",
        string="Item Padrão",
        required=True,
        readonly=True,
    )
    diff_html = fields.Html(string="Alterações", readonly=True, sanitize=False)

    def create_for_item(self, item):
        """Create and return the wizard record for one conflicting item.

        :param item: a single dfe_nfe_escrit_item whose linked default differs
        :return: the created wizard record
        """
        item.ensure_one()
        defaults = item.likely_item_defaults_id
        new_vals = item._default_values_from_item()
        return self.create(
            {
                "item_id": item.id,
                "defaults_id": defaults.id,
                "diff_html": self._build_diff_html(item, defaults, new_vals),
            }
        )

    def _build_diff_html(self, item, defaults, new_vals):
        rows = []
        defaults_model = self.env[
            "l10n_br_dfe_monitor.dfe_nfe_escrit_item_defaults"
        ]
        for _item_field, def_field in item._DEFAULT_TRACKED_FIELDS:
            new_value = new_vals.get(def_field)
            if not item._defaults_field_differs(defaults, def_field, new_value):
                continue
            label = defaults_model._fields[def_field].string
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
        new_vals = self.item_id._default_values_from_item()
        tracked = {
            def_field: new_vals.get(def_field)
            for _item_field, def_field in self.item_id._DEFAULT_TRACKED_FIELDS
        }
        self.defaults_id.write(tracked)
        return {"type": "ir.actions.act_window_close"}
