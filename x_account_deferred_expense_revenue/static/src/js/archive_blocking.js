/** @odoo-module **/

/**
 * archive_blocking.js – account.deferred.entry
 *
 * Gear / Action-menu behaviour (Odoo 19):
 *   - draft state → Delete visible, Archive hidden
 *   - cancelled state → Delete visible, Archive visible
 *   - running, closed states → Archive visible, Delete hidden
 *
 * Custom deleteRecord always redirects to list view after deletion.
 */

import { patch } from "@web/core/utils/patch";
import { FormController } from "@web/views/form/form_controller";

const TARGET_MODELS = {
    "account.deferred.entry": {
        draft: ["draft"],
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
        const isDraft = config.draft.includes(state);
        const isCancel = config.cancel ? config.cancel.includes(state) : false;

        if (isDraft) {
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
            if (items.delete) {
                items.delete.isAvailable = () => !this.model.root.isNew;
            }
            // archive & unarchive remain true (default)
        } else {
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
