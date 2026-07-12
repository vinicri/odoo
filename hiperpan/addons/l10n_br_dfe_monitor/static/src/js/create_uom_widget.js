/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { FormViewDialog } from "@web/views/view_dialogs/form_view_dialog";
import { Many2XAutocomplete } from "@web/views/fields/relational_utils";
import { many2OneField, Many2OneField } from "@web/views/fields/many2one/many2one_field";
import { _t } from "@web/core/l10n/translation";

/**
 * Adds a "Criar Unidade de Medida..." option to the escrituração item's
 * `uom_id` dropdown, next to the standard "Create and edit...". Opens a
 * dedicated wizard (category locked to the product's UoM category, optional
 * conversion factor) instead of the raw uom.uom form, then assigns the
 * created unit back to the field.
 */
const WIZARD_MODEL = "l10n_br_dfe_monitor.create_uom_wizard";

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

class UomMany2XAutocomplete extends Many2XAutocomplete {
    static props = {
        ...Many2XAutocomplete.props,
        onCreateUom: { type: Function, optional: true },
    };

    get optionsSource() {
        const source = super.optionsSource;
        return {
            ...source,
            options: async (request) => {
                const options = await source.options(request);
                if (this.props.onCreateUom) {
                    options.push({
                        label: _t("Criar Unidade de Medida..."),
                        classList: "o_m2o_dropdown_option o_m2o_dropdown_option_create_edit",
                        action: () => this.props.onCreateUom(),
                    });
                }
                return options;
            },
        };
    }
}

export class UomMany2OneField extends Many2OneField {
    static components = {
        ...Many2OneField.components,
        Many2XAutocomplete: UomMany2XAutocomplete,
    };

    setup() {
        super.setup();
        this.orm = useService("orm");
        this.dialog = useService("dialog");
    }

    get Many2XAutocompleteProps() {
        return {
            ...super.Many2XAutocompleteProps,
            onCreateUom: () => this.onCreateUom(),
        };
    }

    async onCreateUom() {
        const record = this.props.record;
        const categoryId = readId(record.data.product_uom_category_id);
        const likelyUomMultiplier = record.data.likely_uom_multiplier;
        const likelyUomRounding = record.data.likely_uom_rounding;
        if (!categoryId) {
            return;
        }

        const wizardIds = await this.orm.create(WIZARD_MODEL, [
            { category_id: categoryId, multiplier: likelyUomMultiplier, rounding: likelyUomRounding },
        ]);
        const wizardId = Array.isArray(wizardIds) ? wizardIds[0] : wizardIds;

        // FormViewDialog + its NATIVE save button (no custom <footer> in the
        // wizard arch): the native save calls saveRecord -> this.props.close(),
        // which closes only THIS dialog instead of cascade-closing the
        // escrituração/item modals underneath it.
        this.dialog.add(FormViewDialog, {
            resModel: WIZARD_MODEL,
            resId: wizardId,
            title: _t("Criar Unidade de Medida"),
            onRecordSaved: async (wizardRecord) => {
                await this.orm.call(WIZARD_MODEL, "action_create_uom", [
                    [wizardRecord.resId],
                ]);
                const [wiz] = await this.orm.read(
                    WIZARD_MODEL,
                    [wizardRecord.resId],
                    ["created_uom_id"]
                );
                const created = wiz && wiz.created_uom_id;
                const uomId = readId(created);
                if (uomId) {
                    const displayName = Array.isArray(created) ? created[1] : "";
                    await record.update({ [this.props.name]: [uomId, displayName] });
                }
            },
        });
    }
}

export const uomMany2OneField = {
    ...many2OneField,
    component: UomMany2OneField,
};

registry.category("fields").add("dfe_uom_many2one", uomMany2OneField);
