/** @odoo-module **/

/**
 * archive_blocking.js – service.planning
 *
 * Gear / Action-menu behaviour (Odoo 19):
 *   - active state AND no related documents → Delete visible, Archive hidden
 *   - cancelled state → Delete visible, Archive visible
 *   - done state OR has related documents → Archive visible, Delete hidden
 *
 * Custom deleteRecord always redirects to list view after deletion.
 */

import { patch } from "@web/core/utils/patch";
import { FormController } from "@web/views/form/form_controller";

const TARGET_MODELS = {
    "service.planning": {
        draft: ["active"],
        cancel: ["cancelled"],
    }
};

patch(FormController.prototype, {
    getStaticActionMenuItems() {
        const items = super.getStaticActionMenuItems(...arguments);

        const resModel = this.model?.root?.resModel;
        if (!TARGET_MODELS[resModel]) return items;

        const state = this.model?.root?.data?.state;
        if (state === undefined || state === null) return items;

        const config = TARGET_MODELS[resModel];
        const hasRelated = this.model?.root?.data?.has_related_document;
        const isDraft = config.draft.includes(state);
        const isCancel = config.cancel ? config.cancel.includes(state) : false;

        // If the document is new/draft (active state) and has NO related documents:
        if (isDraft && !hasRelated) {
            if (items.delete) {
                items.delete.isAvailable = () => !this.model.root.isNew;
            }
            if (items.archive) {
                items.archive.isAvailable = () => false;
            }
            if (items.unarchive) {
                items.unarchive.isAvailable = () => false;
            }
        } else if (isCancel) {
            // If the document is cancelled, both Delete and Archive/Unarchive are available
            if (items.delete) {
                items.delete.isAvailable = () => !this.model.root.isNew;
            }
            // archive & unarchive remain true (default)
        } else {
            // If the document is done OR is connected to other documents (SPK/RC):
            if (items.delete) {
                items.delete.isAvailable = () => false;
            }
        }

        return items;
    },

    async deleteRecord() {
        const resModel = this.model?.root?.resModel;
        if (TARGET_MODELS[resModel]) {
            this.deleteRecordsWithConfirmation({
                confirm: async () => {
                    await this.model.root.delete();
                    this.env.config.historyBack();
                },
            }, [this.model.root]);
        } else {
            super.deleteRecord(...arguments);
        }
    },
});
