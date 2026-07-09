/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { FormViewDialog } from "@web/views/view_dialogs/form_view_dialog";
import { standardWidgetProps } from "@web/views/widgets/standard_widget_props";
import { Component } from "@odoo/owl";

/**
 * Button next to the escrituração item's `product_id` field. It opens a wizard
 * (pre-populated from the item's processed NF-e line) to create a new product,
 * then assigns the created product back to the item — even when the item is
 * still unsaved (a NewId line inside its modal).
 */
const WIZARD_MODEL = "l10n_br_dfe_monitor.create_product_wizard";

function readId(value) {
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

export class CreateProductButton extends Component {
    static template = "l10n_br_dfe_monitor.CreateProductButton";
    static props = { ...standardWidgetProps };

    setup() {
        this.orm = useService("orm");
        this.dialog = useService("dialog");
    }

    get disabled() {
        // Needs the processed NF-e line to pre-fill fiscal data.
        return !readId(this.props.record.data.proc_nfe_item_id);
    }

    async onClick() {
        const record = this.props.record;
        const procItemId = readId(record.data.proc_nfe_item_id);
        if (!procItemId) {
            return;
        }
        // Pre-create the transient wizard record (INSERT into the *wizard*
        // table, NOT product) so it opens pre-filled and we hold its id.
        const defaults = await this.orm.call(WIZARD_MODEL, "default_get_from_item", [
            procItemId,
        ]);
        const wizardIds = await this.orm.create(WIZARD_MODEL, [defaults]);
        const wizardId = Array.isArray(wizardIds) ? wizardIds[0] : wizardIds;

        // Use the FormViewDialog with its NATIVE "Save & Close" button (no custom
        // <footer> in the arch). Native save calls saveRecord -> this.props.close(),
        // which closes only THIS dialog — it does not cascade-close the
        // escrituração/item modals underneath (a custom footer object-button
        // routed through the action service is what caused that cascade before).
        //
        // The product is created in onRecordSaved: the wizard record (with the
        // user's edits) is already saved at that point, so we run
        // action_create_product and read the created product back.
        this.dialog.add(FormViewDialog, {
            resModel: WIZARD_MODEL,
            resId: wizardId,
            title: "Criar Produto",
            onRecordSaved: async (wizardRecord) => {
                await this.orm.call(WIZARD_MODEL, "action_create_product", [
                    [wizardRecord.resId],
                ]);
                const [wiz] = await this.orm.read(
                    WIZARD_MODEL,
                    [wizardRecord.resId],
                    ["created_product_id"]
                );
                const created = wiz && wiz.created_product_id;
                const productId = readId(created);
                if (productId) {
                    // Many2one fields on the relational model are stored/updated
                    // as an [id, display_name] pair, not an {id, display_name}
                    // object — passing an object silently resolves to false.
                    const displayName = Array.isArray(created) ? created[1] : "";
                    await record.update({ product_id: [productId, displayName] });
                }
            },
        });
    }
}

registry.category("view_widgets").add("dfe_create_product_button", {
    component: CreateProductButton,
});
