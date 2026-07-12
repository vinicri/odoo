/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Many2XAutocomplete } from "@web/views/fields/relational_utils";
import { many2OneField, Many2OneField } from "@web/views/fields/many2one/many2one_field";

/**
 * When the escrituração item's `product_id` dropdown is opened with nothing
 * typed yet, pre-seed the search with the NF-e item's description
 * (proc_nfe_item_id, whose _rec_name is x_prod) so likely matches show up
 * first. As soon as the user types anything, the normal search takes over
 * using exactly what they typed.
 */
function readDisplayName(value) {
    if (Array.isArray(value)) {
        return value[1] || "";
    }
    if (value && typeof value === "object") {
        return value.display_name || "";
    }
    return "";
}

class ProductMany2XAutocomplete extends Many2XAutocomplete {
    static props = {
        ...Many2XAutocomplete.props,
        seedName: { type: String, optional: true },
    };

    search(name) {
        const seed = this.props.seedName;
        if (!name && seed) {
            return super.search(seed);
        }
        return super.search(name);
    }
}

export class ProductMany2OneField extends Many2OneField {
    static components = {
        ...Many2OneField.components,
        Many2XAutocomplete: ProductMany2XAutocomplete,
    };

    get Many2XAutocompleteProps() {
        return {
            ...super.Many2XAutocompleteProps,
            seedName: readDisplayName(this.props.record.data.proc_nfe_item_id),
        };
    }
}

export const productMany2OneField = {
    ...many2OneField,
    component: ProductMany2OneField,
};

registry.category("fields").add("dfe_product_many2one", productMany2OneField);
