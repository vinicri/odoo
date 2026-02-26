/** @odoo-module **/

import { registry } from "@web/core/registry";
import { BooleanField, booleanField } from "@web/views/fields/boolean/boolean_field";
import { useService } from "@web/core/utils/hooks";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { _t } from "@web/core/l10n/translation";
import { markup, onMounted, onPatched } from "@odoo/owl";

/**
 * Custom BooleanField widget that shows a Yes/No confirmation dialog when
 * the product changes to a "produção própria" type (fiscal type 03/04).
 *
 * On "Sim" → sets the field to True (include IPI in ICMS BC).
 * On "Não" → keeps the field as False.
 *
 * Handles two rendering scenarios for the `invisible` attribute:
 * - CSS display (widget always mounted): detected via onPatched product tracking
 * - t-if conditional (widget mounts/unmounts): detected via onMounted + isDirty
 */
export class IpiIcmsConfirmationField extends BooleanField {
    setup() {
        super.setup();
        this.dialog = useService("dialog");
        this._prevProductId = this._getProductId();
        this._pendingDialog = false;

        // Handles the case where `invisible` uses t-if: the widget only mounts
        // when is_production_fiscal_type becomes True (product just changed).
        // We use isDirty to avoid showing on existing records when the form loads.
        onMounted(() => {
            const isProduction = this.props.record.data.is_production_fiscal_type;
            const value = this.props.record.data.include_ipi_in_icms_bc;
            const productId = this._getProductId();
            const isDirty = this.props.record.isDirty ?? false;

            if (productId && isProduction && !value && isDirty && !this._pendingDialog) {
                this._pendingDialog = true;
                Promise.resolve().then(() => {
                    if (this._pendingDialog) {
                        this._showConfirmation();
                    }
                });
            }
        });

        // Handles the case where the widget is already mounted and the user
        // changes the product to another production-type product.
        onPatched(() => {
            const currentProductId = this._getProductId();
            const isProduction = this.props.record.data.is_production_fiscal_type;

            if (
                currentProductId &&
                currentProductId !== this._prevProductId &&
                isProduction &&
                !this._pendingDialog
            ) {
                this._pendingDialog = true;
                this._showConfirmation();
            }

            this._prevProductId = currentProductId;
        });
    }

    _getProductId() {
        const val = this.props.record.data.product_id;
        if (Array.isArray(val)) return val[0];
        if (val && typeof val === "object" && val.id) return val.id;
        if (typeof val === "number") return val;
        return null;
    }

    _getProductName() {
        const val = this.props.record.data.product_id;
        if (Array.isArray(val)) return val[1] || "";
        if (val && typeof val === "object" && val.display_name) return val.display_name;
        return "";
    }

    _showConfirmation() {
        const productName = this._getProductName();
        const message = markup(
            `O produto '${productName}' é produção própria do estabelecimento e está sujeito ` +
            "a incidência de IPI.<br><br>O IPI deve ser incluído na base de cálculo do ICMS se o " +
            "comprador da mercadoria não for revendê-la ou utilizá-la como matéria prima " +
            "para outro produto. Caso o destinatário não seja contribuinte do ICMS, também " +
            "deve-se incluir o IPI na base de cálculo do ICMS.<br><br>" +
            "<b>OBRIGAÇÃO FISCAL: para não incluir o IPI, o comprador deve enviar uma ordem de compra " +
            "explicitando que a mercadoria será revendida ou utilizada como matéria prima " +
            "para outro produto. Caso contrário, o IPI deve ser incluído na base de cálculo " +
            "do ICMS.</b><br><br>" +
            "Deseja incluir o IPI na base de cálculo do ICMS?"
        );

        this.dialog.add(ConfirmationDialog, {
            title: _t("Incluir IPI na Base de Cálculo do ICMS?"),
            body: message,
            confirmLabel: _t("Sim"),
            cancelLabel: _t("Não"),
            confirm: () => {
                this.props.record.update({ include_ipi_in_icms_bc: true });
                this._pendingDialog = false;
            },
            cancel: () => {
                this._pendingDialog = false;
            },
        }, {
            onClose: () => {
                this._pendingDialog = false;
            },
        });
    }
}

export const ipiIcmsConfirmationField = {
    ...booleanField,
    component: IpiIcmsConfirmationField,
};

registry.category("fields").add("ipi_icms_confirmation", ipiIcmsConfirmationField);
