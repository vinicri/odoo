/** @odoo-module **/

import { registry } from "@web/core/registry";
import { PhoneField } from "@web/views/fields/phone/phone_field";
import { useService } from "@web/core/utils/hooks";
import { patch } from "@web/core/utils/patch";

// Create a patched version of PhoneField
export class BrazilianPhoneField extends PhoneField {
    setup() {
        super.setup();
        this.orm = useService("orm");
    }

    onFocus() {
        super.onFocus();
        this._handleFocus();
    }

    // Override the input event to also check on input
    onInput(ev) {
        super.onInput(ev);
        // If the field becomes empty, check if we should prepopulate
        if (!this.props.value || this.props.value.trim() === '') {
            this._handleFocus();
        }
    }

    async _handleFocus() {
        // Only proceed if the field is empty
        if (!this.props.value || this.props.value.trim() === '') {
            try {
                console.log("Phone field focused, checking country...");
                console.log("Props:", this.props);
                console.log("Environment:", this.env);
                
                // Method 1: Try to get country from props
                let countryCode = null;
                
                if (this.props.record && this.props.record.data && this.props.record.data.country_id) {
                    const countryData = this.props.record.data.country_id;
                    console.log("Country data from record:", countryData);
                    countryCode = countryData[1];
                }
                
                // Method 2: Try to get country from form context
                if (!countryCode && this.env && this.env.services && this.env.services.form) {
                    const form = this.env.services.form;
                    console.log("Form services:", form);
                    
                    if (form.activeFields && form.activeFields.country_id) {
                        const countryValue = form.activeFields.country_id.value;
                        console.log("Country value from form:", countryValue);
                        countryCode = countryValue[1];
                    }
                }
                
                // Method 3: Try to get country from parent component
                if (!countryCode && this.props.record && this.props.record.resId) {
                    try {
                        const result = await this.orm.read('res.partner', [this.props.record.resId], ['country_id']);
                        if (result && result[0] && result[0].country_id) {
                            countryCode = result[0].country_id[1];
                            console.log("Country code from ORM:", countryCode);
                        }
                    } catch (ormError) {
                        console.warn("ORM read failed:", ormError);
                    }
                }
                
                // Method 4: Try to get country from the DOM
                if (!countryCode) {
                    try {
                        const countryField = document.querySelector('field[name="country_id"] input, field[name="country_id"] select');
                        if (countryField) {
                            const countryValue = countryField.value;
                            console.log("Country value from DOM:", countryValue);
                            // Try to extract country code from the value
                            if (countryValue.includes('BR') || countryValue.includes('Brazil')) {
                                countryCode = 'BR';
                            }
                        }
                    } catch (domError) {
                        console.warn("DOM access failed:", domError);
                    }
                }
                
                // Check if country is Brazil and prepopulate
                if (countryCode === 'BR') {
                    console.log("Country is Brazil, prepopulating with '34'");
                    this.update({ value: "34" });
                } else {
                    console.log("Country is not Brazil:", countryCode);
                }
                
            } catch (error) {
                console.warn("Could not determine country for phone field:", error);
            }
        }
    }
}

// Register the field
registry.category("fields").add("l10n_br_phone", BrazilianPhoneField);

// Also try alternative registration method for compatibility
if (window.odoo && window.odoo.define) {
    window.odoo.define('l10n_br_base.phone_field', function (require) {
        "use strict";
        return BrazilianPhoneField;
    });
}

// Export for debugging
window.BrazilianPhoneField = BrazilianPhoneField;
