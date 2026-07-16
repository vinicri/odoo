/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { FormViewDialog } from "@web/views/view_dialogs/form_view_dialog";
import { standardWidgetProps } from "@web/views/widgets/standard_widget_props";
import { Component } from "@odoo/owl";

/**
 * Button next to the "Criar Produto" wizard's Preço de Venda field. Opens a
 * small calculator (cost from the NF-e line, margin or final price editable,
 * each recalculating the other) and assigns the resulting price to
 * list_price when confirmed.
 */
const WIZARD_MODEL = "l10n_br_dfe_monitor.price_calculator_wizard";

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

export class PriceCalculatorButton extends Component {
    static template = "l10n_br_dfe_monitor.PriceCalculatorButton";
    static props = { ...standardWidgetProps };

    setup() {
        this.orm = useService("orm");
        this.dialog = useService("dialog");
    }

    get disabled() {
        // Needs the processed NF-e line for the cost basis.
        return !readId(this.props.record.data.proc_nfe_item_id);
    }

    async onClick() {
        const record = this.props.record;
        const procItemId = readId(record.data.proc_nfe_item_id);
        if (!procItemId) {
            return;
        }

        const wizardIds = await this.orm.create(WIZARD_MODEL, [
            { proc_nfe_item_id: procItemId },
        ]);
        const wizardId = Array.isArray(wizardIds) ? wizardIds[0] : wizardIds;

        // FormViewDialog + its NATIVE save button (no custom <footer> in the
        // wizard arch): the native save calls saveRecord -> this.props.close(),
        // which closes only THIS dialog instead of cascade-closing the
        // create-product modal underneath it.
        this.dialog.add(FormViewDialog, {
            resModel: WIZARD_MODEL,
            resId: wizardId,
            title: "Calculadora de Preço de Venda",
            onRecordSaved: async (wizardRecord) => {
                const [wiz] = await this.orm.read(
                    WIZARD_MODEL,
                    [wizardRecord.resId],
                    ["unit_price"]
                );
                if (wiz && wiz.unit_price) {
                    await record.update({ list_price: wiz.unit_price });
                }
            },
        });
    }
}

registry.category("view_widgets").add("dfe_price_calculator_button", {
    component: PriceCalculatorButton,
});
