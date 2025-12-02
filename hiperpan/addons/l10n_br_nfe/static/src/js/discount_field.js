/** @odoo-module **/

import { registry } from "@web/core/registry";
import { FloatField, floatField } from "@web/views/fields/float/float_field";
import { useService } from "@web/core/utils/hooks";
import { useRef } from "@odoo/owl";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { _t } from "@web/core/l10n/translation";
import { stealFocus } from "@l10n_br_nfe/js/utils/focus_utils";

/**
 * Widget personalizado para o campo total_discount que mostra um popup
 * de confirmação quando o usuário foca no campo e há itens com desconto.
 */
export class DiscountWarningField extends FloatField {
    setup() {
        super.setup();
        this.dialog = useService("dialog");
        this._warningShown = false;
        this._dialogClosing = false;
        // Get reference to the input element (same ref name used by FloatField)
        this.numpadDecimalRef = useRef("numpadDecimal");
    }

    // Override the correct method name from FloatField template (t-on-focusin="onFocusIn")
    onFocusIn() {
        super.onFocusIn();
        
        // Se o dialog acabou de fechar, não mostra novamente (evita loop)
        if (this._dialogClosing) {
            return;
        }
        
        // Evita mostrar o warning múltiplas vezes na mesma sessão de edição
        if (!this._warningShown) {
            this._checkAndShowWarning();
        }
    }

    async _checkAndShowWarning() {
        try {
            const record = this.props.record;
            if (!record || !record.data) {
                return;
            }

            // Obtém as linhas do documento
            const invoiceLines = record.data.invoice_line_ids;
            if (!invoiceLines || !invoiceLines.records) {
                return;
            }

            // Filtra itens com desconto > 0
            const itemsWithDiscount = [];
            for (const line of invoiceLines.records) {
                const discountValue = line.data.discount_value || 0;
                if (discountValue > 0) {
                    const productName =
                        (line.data.product_id && line.data.product_id[1]) ||
                        line.data.product_description ||
                        "Item sem nome";
                    const unitDiscountValue = line.data.unit_discount_value || 0;
                    const unitDiscountPercent = line.data.unit_discount_percent || 0;

                    itemsWithDiscount.push({
                        name: productName,
                        discountValue: discountValue.toFixed(2),
                        unitDiscountValue: unitDiscountValue.toFixed(2),
                        unitDiscountPercent: unitDiscountPercent.toFixed(4),
                    });
                }
            }

            // Se há itens com desconto, mostra o dialog
            if (itemsWithDiscount.length > 0) {
                this._warningShown = true;

                // Monta a mensagem com a lista de itens
                const itemsList = itemsWithDiscount
                    .map(
                        (item) =>
                            `• ${item.name}\n  Desconto do item: R$ ${item.discountValue} | Por unidade: R$ ${item.unitDiscountValue} | Percentual: ${item.unitDiscountPercent}%`
                    )
                    .join("\n\n");

                const message =
                    "Os seguintes itens já possuem desconto configurado e terão seus valores sobrescritos se você alterar o desconto total:\n\n" +
                    itemsList +
                    "\n\nQuando você altera o desconto total, o valor do desconto é distribuído proporcionalmente entre os itens da nota fiscal, " +
                    "apagando os valores de desconto por item. Para manter o desconto por item, não altere o desconto total e adicione o desconto somente nos itens que deseja alterar.";

                // Flag para saber se o usuário cancelou
                let userCancelled = false;

                // Handler para quando o dialog fechar (por qualquer meio)
                const onDialogClose = () => {
                    this._dialogClosing = true;
                    
                    // Se o usuário cancelou, tira o foco DEPOIS que o dialog fecha
                    // (o dialog restaura o foco ao fechar, então precisamos fazer isso depois)
                    if (userCancelled) {
                        stealFocus();
                    }
                    
                    // Reseta o flag após um pequeno delay para evitar o loop de focus
                    setTimeout(() => {
                        this._dialogClosing = false;
                    }, 150);
                };

                this.dialog.add(ConfirmationDialog, {
                    title: _t("Atenção: Itens com desconto existente"),
                    body: message,
                    confirmLabel: _t("Alterar o desconto total"),
                    cancelLabel: _t("Manter os descontos por item"),
                    confirm: () => {
                        // Usuário confirmou, permite a edição
                    },
                    cancel: () => {
                        // Marca que o usuário cancelou (o blur será feito no onClose)
                        userCancelled = true;
                    },
                }, {
                    onClose: onDialogClose,
                });
            }
        } catch (error) {
            console.warn("Erro ao verificar itens com desconto:", error);
        }
    }

    // Override the correct method name from FloatField template (t-on-focusout="onFocusOut")
    onFocusOut() {
        super.onFocusOut();
        // Só reseta o flag se o dialog não está fechando (evita loop)
        if (!this._dialogClosing) {
            this._warningShown = false;
        }
    }
}

// Define as propriedades do widget
export const discountWarningField = {
    ...floatField,
    component: DiscountWarningField,
};

// Registra o widget
registry.category("fields").add("discount_warning", discountWarningField);
