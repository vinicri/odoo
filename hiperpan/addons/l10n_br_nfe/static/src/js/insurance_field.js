/** @odoo-module **/

import { registry } from "@web/core/registry";
import { _t } from "@web/core/l10n/translation";
import { ConfirmationField, confirmationField } from "@l10n_br_nfe/js/fields/confirmation_field";
import { getItemsWithNonZeroValue } from "@l10n_br_nfe/js/utils/total_fields_utils";
/**
 * Widget personalizado para o campo total_insurance que mostra um popup
 * de confirmação quando o usuário foca no campo e há itens com seguro.
 * 
 * Estende ConfirmationField para reusar a lógica de confirmação.
 */
export class InsuranceWarningField extends ConfirmationField {
    
    /**
     * Verifica se existem itens com seguro e retorna a lista.
     * @returns {Array} Lista de itens com seguro
     */
    _getItemsWithInsurance() {
        const linesWithInsurance =  getItemsWithNonZeroValue(this.props.record, "insurance_value");

        return linesWithInsurance.map(line => {
          const productName = (line.data.product_id && line.data.product_id[1]) ||
                    line.data.product_description ||
                    "Item sem nome";
          const insuranceValue = line.data.insurance_value || 0;
          return {
            name: productName,
            insuranceValue: insuranceValue.toFixed(2),
          };
        });
    }

    /**
     * Só mostra o warning se existirem itens com desconto.
     */
    async shouldShowWarning() {
        return this._getItemsWithInsurance().length > 0;
    }

    /**
     * Retorna as props do dialog com a mensagem customizada.
     */
    getDialogProps() {
        const itemsWithInsurance = this._getItemsWithInsurance();
        
        const itemsList = itemsWithInsurance
            .map(
                (item) =>
                    `• ${item.name}\n  Seguro do item: R$ ${item.insuranceValue}`
            )
            .join("\n\n");

        const message =
            "Os seguintes itens já possuem seguro configurado e terão seus valores sobrescritos se você alterar o seguro total:\n\n" +
            itemsList +
            "\n\nQuando você altera o seguro total, o valor do seguro é distribuído proporcionalmente entre os itens da nota fiscal, " +
            "apagando os valores de seguro por item. Para manter o seguro por item, não altere o seguro total e adicione o seguro somente nos itens que deseja alterar.";

        return {
            title: _t("Atenção: Itens com seguro existente"),
            body: message,
            confirmLabel: _t("Alterar o seguro total"),
            cancelLabel: _t("Manter os seguros por item"),
        };
    }
}

// Define as propriedades do widget
export const insuranceWarningField = {
    ...confirmationField,
    component: InsuranceWarningField,
};

// Registra o widget
registry.category("fields").add("insurance_warning", insuranceWarningField);
