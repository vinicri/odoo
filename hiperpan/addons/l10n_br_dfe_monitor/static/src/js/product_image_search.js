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

        onWillStart(() => {
            const existing = this.props.record.data.image_search_results_json;
            if (existing) {
                this._setCandidatesFromJson(existing);
            } else if ((this.props.record.data.name || "").trim()) {
                // Auto-search once when the wizard opens with a name already
                // filled in (from the NF-e item). Not awaited: onWillStart
                // blocks the whole modal's first render, so the dialog must
                // open immediately and ready to edit while the search (a
                // network call to Google/SerpApi) runs in the background,
                // showing its own spinner in the image area. Failures are
                // shown inline, not as a blocking error dialog, since image
                // search is optional.
                this.search();
            }
        });
    }

    get recordId() {
        return this.props.record.resId;
    }

    get barcode() {
        return (this.props.record.data.barcode || "").trim();
    }

    get showBarcodeSearch() {
        // Offer the more precise barcode-based search once a barcode is
        // set and the user hasn't picked an image yet.
        return !!this.barcode && !this.state.selectedUrl;
    }

    _setCandidatesFromJson(jsonStr) {
        try {
            this.state.candidates = JSON.parse(jsonStr) || [];
        } catch {
            this.state.candidates = [];
        }
    }

    async search() {
        await this._runSearch("action_search_product_images");
    }

    async searchByBarcode() {
        await this._runSearch("action_search_product_images_by_barcode");
    }

    async _runSearch(methodName) {
        this.state.loading = true;
        this.state.error = null;
        try {
            await this.props.record.model.orm.call(
                WIZARD_MODEL,
                methodName,
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
