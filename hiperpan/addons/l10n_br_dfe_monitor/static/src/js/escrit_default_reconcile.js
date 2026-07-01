/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { FormController } from "@web/views/form/form_controller";
import { useService } from "@web/core/utils/hooks";

/**
 * After saving an escrituração, reconcile its items against the item-defaults
 * table. Missing defaults are created silently server-side; for each item that
 * differs from its stored default, a confirmation wizard is opened — one wizard
 * per conflicting item, shown one after another.
 *
 * Only the escrituração form triggers this; every other form is left untouched.
 */
const ESCRIT_MODEL = "l10n_br_dfe_monitor.dfe_nfe_escrit";
const ITEM_MODEL = "l10n_br_dfe_monitor.dfe_nfe_escrit_item";

patch(FormController.prototype, {
    setup() {
        super.setup();
        this._escritActionService = useService("action");
    },

    async save(params) {
        const saved = await super.save(params);
        if (saved && this.props.resModel === ESCRIT_MODEL) {
            const resId = this.model.root.resId;
            if (resId) {
                await this._reconcileEscritItemDefaults(resId);
            }
        }
        return saved;
    },

    async _reconcileEscritItemDefaults(resId) {
        const orm = this.model.orm;
        const conflictIds = await orm.call(
            ESCRIT_MODEL,
            "reconcile_item_defaults",
            [[resId]]
        );
        // Open one wizard per conflicting item, waiting for each to close before
        // moving on to the next. The server builds the wizard record and returns
        // its id; the action is assembled here so it always carries `views`.
        for (const itemId of conflictIds || []) {
            const wizardId = await orm.call(
                ITEM_MODEL,
                "create_default_update_wizard",
                [[itemId]]
            );
            if (wizardId) {
                await new Promise((resolve) => {
                    this._escritActionService.doAction(
                        {
                            type: "ir.actions.act_window",
                            name: "Atualizar Item Padrão?",
                            res_model:
                                "l10n_br_dfe_monitor.escrit_item_default_update_wizard",
                            res_id: wizardId,
                            views: [[false, "form"]],
                            view_mode: "form",
                            target: "new",
                        },
                        { onClose: () => resolve() }
                    );
                });
            }
        }
    },
});
