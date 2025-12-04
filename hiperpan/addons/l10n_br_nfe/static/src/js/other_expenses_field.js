/** @odoo-module **/

import { registry } from "@web/core/registry";
import { _t } from "@web/core/l10n/translation";
import { ConfirmationField, confirmationField } from "@l10n_br_nfe/js/fields/confirmation_field";
import { getItemsWithNonZeroValue } from "@l10n_br_nfe/js/utils/total_fields_utils";
/**
 * Widget personalizado para o campo total_other_expenses que mostra um popup
 * de confirmação quando o usuário foca no campo e há itens com seguro.
 * 
 * Estende ConfirmationField para reusar a lógica de confirmação.
 */
export class OtherExpensesWarningField extends ConfirmationField {
    
    /**
     * Verifica se existem itens com seguro e retorna a lista.
     * @returns {Array} Lista de itens com seguro
     */
    _getItemsWithOtherExpenses() {
        const linesWithOtherExpenses =  getItemsWithNonZeroValue(this.props.record, "other_expenses_value");

        return linesWithOtherExpenses.map(line => {
          const productName = (line.data.product_id && line.data.product_id[1]) ||
                    line.data.product_description ||
                    "Item sem nome";
          const otherExpensesValue = line.data.other_expenses_value || 0;
          return {
            name: productName,
            otherExpensesValue: otherExpensesValue.toFixed(2),
          };
        });
    }

    /**
     * Só mostra o warning se existirem itens com desconto.
     */
    async shouldShowWarning() {
        return this._getItemsWithOtherExpenses().length > 0;
    }

    /**
     * Retorna as props do dialog com a mensagem customizada.
     */
    getDialogProps() {
        const itemsWithOtherExpenses = this._getItemsWithOtherExpenses();
        
        const itemsList = itemsWithOtherExpenses
            .map(
                (item) =>
                    `• ${item.name}\n  Outras Despesas Acessórias do item: R$ ${item.otherExpensesValue}`
            )
            .join("\n\n");

        const message =
            "Os seguintes itens já possuem outras despesas acessórias configuradas e terão seus valores sobrescritos se você alterar o total de outras despesas acessórias:\n\n" +
            itemsList +
            "\n\nQuando você altera o total de outras despesas acessórias, o valor das outras despesas acessórias é distribuído proporcionalmente entre os itens da nota fiscal, " +
            "apagando os valores de outras despesas acessórias por item. Para manter as outras despesas acessórias por item, não altere o total de outras despesas acessórias e adicione as outras despesas acessórias somente nos itens que deseja alterar.";

        return {
            title: _t("Atenção: Itens com outras despesas acessórias existentes"),
            body: message,
            confirmLabel: _t("Alterar o total de outras despesas acessórias"),
            cancelLabel: _t("Manter as outras despesas acessórias por item"),
        };
    }
}

// Define as propriedades do widget
export const otherExpensesWarningField = {
    ...confirmationField,
    component: OtherExpensesWarningField,
};

// Registra o widget
registry.category("fields").add("other_expenses_warning", otherExpensesWarningField);
