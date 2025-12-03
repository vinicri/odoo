/** @odoo-module **/

import { registry } from "@web/core/registry";
import { floatField } from "@web/views/fields/float/float_field";
import { _t } from "@web/core/l10n/translation";
import { ConfirmationField, confirmationField } from "@l10n_br_nfe/js/fields/confirmation_field";

/**
 * Widget personalizado para o campo total_discount que mostra um popup
 * de confirmação quando o usuário foca no campo e há itens com desconto.
 * 
 * Estende ConfirmationField para reusar a lógica de confirmação.
 */
export class DiscountWarningField extends ConfirmationField {
    
    /**
     * Verifica se existem itens com desconto e retorna a lista.
     * @returns {Array} Lista de itens com desconto
     */
    _getItemsWithDiscount() {
        const record = this.props.record;
        if (!record || !record.data) {
            return [];
        }

        const invoiceLines = record.data.invoice_line_ids;
        if (!invoiceLines || !invoiceLines.records) {
            return [];
        }

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
        return itemsWithDiscount;
    }

    /**
     * Só mostra o warning se existirem itens com desconto.
     */
    async shouldShowWarning() {
        return this._getItemsWithDiscount().length > 0;
    }

    /**
     * Retorna as props do dialog com a mensagem customizada.
     */
    getDialogProps() {
        const itemsWithDiscount = this._getItemsWithDiscount();
        
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

        return {
            title: _t("Atenção: Itens com desconto existente"),
            body: message,
            confirmLabel: _t("Alterar o desconto total"),
            cancelLabel: _t("Manter os descontos por item"),
        };
    }
}

// Define as propriedades do widget
export const discountWarningField = {
    ...confirmationField,
    component: DiscountWarningField,
};

// Registra o widget
registry.category("fields").add("discount_warning", discountWarningField);
