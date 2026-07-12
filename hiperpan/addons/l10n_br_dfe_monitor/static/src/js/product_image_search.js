/** @odoo-module **/

import { registry } from "@web/core/registry";
import { standardWidgetProps } from "@web/views/widgets/standard_widget_props";
import { Component, onWillStart, useState } from "@odoo/owl";

/**
 * Area at the top of the "Criar Produto" wizard: on open, searches Google
 * Images for the (pre-filled) product name and shows up to 5 candidate
 * thumbnails (already filtered server-side to a minimum resolution).
 * Clicking one downloads/validates/resizes it server-side and stores it as
 * the wizard's image_1920, which is then included when the product is
 * created.
 */
const WIZARD_MODEL = "l10n_br_dfe_monitor.create_product_wizard";

export class ProductImageSearch extends Component {
    static template = "l10n_br_dfe_monitor.ProductImageSearch";
    static props = { ...standardWidgetProps };

    setup() {
        this.state = useState({
            loading: false,
            error: null,
            candidates: [],
            selectedUrl: null,
        });

        onWillStart(async () => {
            const existing = this.props.record.data.image_search_results_json;
            if (existing) {
                this._setCandidatesFromJson(existing);
            } else if ((this.props.record.data.name || "").trim()) {
                // Auto-search once when the wizard opens with a name already
                // filled in (from the NF-e item). Failures here (e.g. Google
                // credentials not configured) are shown inline, not as a
                // blocking error dialog, since image search is optional.
                await this.search();
            }
        });
    }

    get recordId() {
        return this.props.record.resId;
    }

    _setCandidatesFromJson(jsonStr) {
        try {
            this.state.candidates = JSON.parse(jsonStr) || [];
        } catch {
            this.state.candidates = [];
        }
    }

    async search() {
        this.state.loading = true;
        this.state.error = null;
        try {
            await this.props.record.model.orm.call(
                WIZARD_MODEL,
                "action_search_product_images",
                [[this.recordId]]
            );
            const [wiz] = await this.props.record.model.orm.read(
                WIZARD_MODEL,
                [this.recordId],
                ["image_search_results_json"]
            );
            this._setCandidatesFromJson(wiz && wiz.image_search_results_json);
        } catch (e) {
            this.state.candidates = [];
            this.state.error = (e && e.data && e.data.message) || e.message || String(e);
        } finally {
            this.state.loading = false;
        }
    }

    async selectImage(candidate) {
        this.state.loading = true;
        this.state.error = null;
        try {
            await this.props.record.model.orm.call(
                WIZARD_MODEL,
                "action_select_product_image",
                [[this.recordId], candidate.image_url]
            );
            // image_1920 was written server-side (not via record.update), so
            // reload the record to pick it up in the form's Image field.
            await this.props.record.load();
            this.state.selectedUrl = candidate.image_url;
        } catch (e) {
            this.state.error = (e && e.data && e.data.message) || e.message || String(e);
        } finally {
            this.state.loading = false;
        }
    }
}

registry.category("view_widgets").add("dfe_product_image_search", {
    component: ProductImageSearch,
});
