/** @odoo-module **/

import { registry } from "@web/core/registry";
import { FloatField, floatField } from "@web/views/fields/float/float_field";
import { useService } from "@web/core/utils/hooks";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { _t } from "@web/core/l10n/translation";
import { stealFocus } from "@l10n_br_nfe/js/utils/focus_utils";

/**
 * Campo genérico que mostra um dialog de confirmação antes de permitir edição.
 * 
 * Pode ser usado de duas formas:
 * 
 * 1. Via XML options (configuração simples):
 *    <field name="my_field" widget="confirmation_field" options="{
 *        'title': 'Atenção',
 *        'message': 'Tem certeza que deseja editar?',
 *        'confirmLabel': 'Sim',
 *        'cancelLabel': 'Não'
 *    }"/>
 * 
 * 2. Estendendo a classe (para lógica customizada):
 *    export class MyCustomField extends ConfirmationField {
 *        async shouldShowWarning() {
 *            // Sua lógica aqui
 *            return true;
 *        }
 *        getDialogProps() {
 *            return {
 *                title: _t("Meu título"),
 *                body: "Minha mensagem",
 *                ...
 *            };
 *        }
 *    }
 */
export class ConfirmationField extends FloatField {
    static props = {
        ...FloatField.props,
        options: { type: Object, optional: true },
    };

    setup() {
        super.setup();
        this.dialog = useService("dialog");
        this._warningShown = false;
        this._dialogClosing = false;
    }

    /**
     * Retorna as opções do campo definidas no XML.
     * @returns {Object}
     */
    get fieldOptions() {
        return this.props.options || {};
    }

    /**
     * Override este método para definir quando o warning deve ser mostrado.
     * Por padrão, sempre mostra (a menos que 'condition' seja false nas options).
     * @returns {Promise<boolean>}
     */
    async shouldShowWarning() {
        // Se condition está definido nas options e é false, não mostra
        if (this.fieldOptions.condition === false) {
            return false;
        }
        return true;
    }

    /**
     * Override este método para customizar as props do dialog.
     * @returns {Object} Props para o ConfirmationDialog
     */
    getDialogProps() {
        const options = this.fieldOptions;
        return {
            title: options.title ? _t(options.title) : _t("Confirmação"),
            body: options.message || _t("Tem certeza que deseja continuar?"),
            confirmLabel: options.confirmLabel ? _t(options.confirmLabel) : _t("Confirmar"),
            cancelLabel: options.cancelLabel ? _t(options.cancelLabel) : _t("Cancelar"),
        };
    }

    /**
     * Chamado quando o usuário confirma o dialog.
     * Override para adicionar lógica customizada.
     */
    onConfirm() {
        // Usuário confirmou, permite a edição
    }

    /**
     * Chamado quando o usuário cancela o dialog.
     * Override para adicionar lógica customizada.
     */
    onCancel() {
        // Usuário cancelou
    }

    // Override do método de focus
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
            // Verifica se deve mostrar o warning
            const shouldShow = await this.shouldShowWarning();
            if (!shouldShow) {
                return;
            }

            this._warningShown = true;

            // Flag para saber se o usuário cancelou
            let userCancelled = false;

            // Handler para quando o dialog fechar
            const onDialogClose = () => {
                this._dialogClosing = true;
                
                // Se o usuário cancelou, tira o foco
                if (userCancelled) {
                    stealFocus();
                }
                
                // Reseta o flag após um pequeno delay para evitar o loop de focus
                setTimeout(() => {
                    this._dialogClosing = false;
                }, 150);
            };

            // Obtém as props do dialog
            const dialogProps = this.getDialogProps();

            this.dialog.add(ConfirmationDialog, {
                ...dialogProps,
                confirm: () => {
                    this.onConfirm();
                },
                cancel: () => {
                    userCancelled = true;
                    this.onCancel();
                },
            }, {
                onClose: onDialogClose,
            });
        } catch (error) {
            console.warn("Erro ao verificar condição do campo:", error);
        }
    }

    onFocusOut() {
        super.onFocusOut();
        // Só reseta o flag se o dialog não está fechando (evita loop)
        if (!this._dialogClosing) {
            this._warningShown = false;
        }
    }
}

// Define as propriedades do widget
export const confirmationField = {
    ...floatField,
    component: ConfirmationField,
    extractProps: (fieldInfo, dynamicInfo) => {
        const props = floatField.extractProps(fieldInfo, dynamicInfo);
        return {
            ...props,
            options: fieldInfo.options || {},
        };
    },
};

// Registra o widget genérico
registry.category("fields").add("confirmation_field", confirmationField);

