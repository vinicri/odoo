/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { FormViewDialog } from "@web/views/view_dialogs/form_view_dialog";
import { standardWidgetProps } from "@web/views/widgets/standard_widget_props";
import { Component } from "@odoo/owl";

/**
 * Button placed next to the escrituração item's `product_id` field. It opens a
 * wizard (pre-populated from the item's processed NF-e line) to create a new
 * product.product, then assigns the created product back to the item — even
 * when the item is still unsaved (a NewId line inside its modal).
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
        // Build the wizard record server-side, pre-filled from the NF-e item.
        const defaults = await this.orm.call(WIZARD_MODEL, "default_get_from_item", [
            procItemId,
        ]);
        const wizardIds = await this.orm.create(WIZARD_MODEL, [defaults]);
        const wizardId = Array.isArray(wizardIds) ? wizardIds[0] : wizardIds;

        this.dialog.add(
            FormViewDialog,
            {
                resModel: WIZARD_MODEL,
                resId: wizardId,
                title: "Criar Produto",
            },
            {
                // The "Criar Produto" button (close="1") stores the new product
                // on created_product_id and closes the dialog. On close, read it
                // back and assign it to the (possibly unsaved) item. Cancelling
                // leaves created_product_id empty, so nothing is assigned.
                onClose: async () => {
                    const [wiz] = await this.orm.read(
                        WIZARD_MODEL,
                        [wizardId],
                        ["created_product_id"]
                    );
                    const created = wiz && wiz.created_product_id;
                    const productId = readId(created);
                    if (productId) {
                        await record.update({
                            product_id: {
                                id: productId,
                                display_name: Array.isArray(created)
                                    ? created[1]
                                    : "",
                            },
                        });
                    }
                },
            }
        );
    }
}

registry.category("view_widgets").add("dfe_create_product_button", {
    component: CreateProductButton,
});
