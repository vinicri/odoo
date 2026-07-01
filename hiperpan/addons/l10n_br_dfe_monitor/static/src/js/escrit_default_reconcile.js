/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { X2ManyFieldDialog } from "@web/views/fields/relational_utils";
import { Dialog } from "@web/core/dialog/dialog";
import { useService } from "@web/core/utils/hooks";
import { Component, xml, markup } from "@odoo/owl";

/**
 * When saving an escrituração item in its modal, reconcile it against the
 * item-defaults table before the line is committed:
 *   - no default yet  -> create one silently;
 *   - default differs -> open a confirmation dialog (current vs. new values)
 *     and wait for the user before committing the line.
 *
 * Works for both editing an existing item and adding a new one. Scoped to the
 * item model, so every other One2many modal is left untouched.
 */
const ITEM_MODEL = "l10n_br_dfe_monitor.dfe_nfe_escrit_item";
const WIZARD_MODEL = "l10n_br_dfe_monitor.escrit_item_default_update_wizard";

// Item fields mirrored into the defaults record. Must match
// DfeNfeEscritItem._DEFAULT_TRACKED_FIELDS on the Python side.
const TRACKED_FIELDS = [
    "product_id",
    "uom_id",
    "own_use",
    "cfop_id",
    "icms_cst_id",
    "ipi_cst_id",
    "pis_cst_id",
    "cofins_cst_id",
];

function readId(value) {
    // Relational fields surface as [id, display_name] (or {id, ...}); scalars
    // (booleans) pass through.
    if (!value) {
        return false;
    }
    if (Array.isArray(value)) {
        return value[0] || false;
    }
    if (typeof value === "object") {
        return value.id || value.resId || false;
    }
    return value;
}

/**
 * Minimal, self-contained confirmation dialog. Its buttons close only this
 * dialog (via this.props.close), so opening/closing it never disturbs the
 * escrituração/item modal stack — unlike a FormViewDialog whose form-view
 * button machinery cascades closes through the whole overlay stack.
 */
export class EscritDefaultUpdateDialog extends Component {
    static components = { Dialog };
    static props = {
        close: Function,
        wizardId: Number,
        diffHtml: { type: String, optional: true },
        orm: Object,
        onConfirmed: { type: Function, optional: true },
    };

    get diffMarkup() {
        return markup(this.props.diffHtml || "");
    }

    async onUpdate() {
        await this.props.orm.call(WIZARD_MODEL, "action_confirm", [
            [this.props.wizardId],
        ]);
        this.props.onConfirmed?.();
        this.props.close();
    }

    onKeep() {
        this.props.close();
    }
}

// Inline template: alert + server-rendered diff table + two buttons.
const TEMPLATE = xml/* xml */ `
    <Dialog title="'Atualizar Item Padrão?'" size="'lg'">
        <div class="alert alert-info" role="alert">
            Já existe um item padrão para este produto/fornecedor com valores
            diferentes. Deseja atualizá-lo com os novos valores?
        </div>
        <div t-out="diffMarkup"/>
        <t t-set-slot="footer">
            <button class="btn btn-primary" t-on-click="onUpdate">Atualizar Padrão</button>
            <button class="btn btn-secondary" t-on-click="onKeep">Manter Atual</button>
        </t>
    </Dialog>
`;
EscritDefaultUpdateDialog.template = TEMPLATE;

patch(X2ManyFieldDialog.prototype, {
    setup() {
        super.setup();
        this._escritDialogService = useService("dialog");
    },

    async save(options) {
        // The original save() destructures { saveAndNew }; the footer buttons
        // call it with a click event (harmless) — but our re-entrant call must
        // pass a real object, so normalise here.
        const saveOptions =
            options && typeof options === "object" && "saveAndNew" in options
                ? options
                : { saveAndNew: false };

        // Second pass (after the dialog closed) or unrelated model: commit now.
        if (this._escritReconcileDone || this.record.resModel !== ITEM_MODEL) {
            return super.save(saveOptions);
        }

        const conflict = await this._escritReconcileConflict();
        if (!conflict) {
            // No conflict (created silently or already up to date): commit now.
            return super.save(saveOptions);
        }

        // A default differs: show the confirmation dialog, then commit the line
        // once it closes (re-invoke save in a fresh macrotask so this dialog's
        // modalRef is valid again after the overlay teardown).
        this._escritReconcileDone = true;
        this._escritDialogService.add(
            EscritDefaultUpdateDialog,
            {
                wizardId: conflict.wizard_id,
                diffHtml: conflict.diff_html,
                orm: this.record.model.orm,
            },
            {
                onClose: () => {
                    setTimeout(() => this.save({ saveAndNew: false }), 0);
                },
            }
        );
        return false;
    },

    /**
     * Reconcile the item's current values against the defaults table. Returns
     * ``{ wizard_id, diff_html }`` when the existing default differs, or a falsy
     * value when nothing needs confirming (missing default created silently).
     */
    async _escritReconcileConflict() {
        const data = this.record.data;
        const procItemId = readId(data.proc_nfe_item_id);
        if (!procItemId) {
            return false;
        }

        const itemValues = {
            proc_nfe_item_id: procItemId,
            dfe_nfe_escrit_id: readId(data.dfe_nfe_escrit_id),
            likely_item_defaults_id: readId(data.likely_item_defaults_id),
        };
        for (const fieldName of TRACKED_FIELDS) {
            const value = data[fieldName];
            itemValues[fieldName] =
                typeof value === "boolean" ? value : readId(value);
        }

        return this.record.model.orm.call(
            ITEM_MODEL,
            "reconcile_default_from_values",
            [itemValues]
        );
    },
});
