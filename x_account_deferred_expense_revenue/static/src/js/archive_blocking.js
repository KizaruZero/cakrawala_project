/** @odoo-module **/

/**
 * archive_blocking.js – account.deferred.entry
 *
 * Gear / Action-menu behaviour (Odoo 19):
 *   - state == 'draft' → Delete visible, Archive hidden
 *   - any other state  → Archive visible, Delete hidden
 *
 * Custom deleteRecord always redirects to list view after deletion.
 */

import { patch } from "@web/core/utils/patch";
import { FormController } from "@web/views/form/form_controller";

const TARGET_MODEL = "account.deferred.entry";
const DRAFT_STATES = ["draft"];

patch(FormController.prototype, {
    getStaticActionMenuItems() {
        const items = super.getStaticActionMenuItems(...arguments);

        const resModel = this.model?.root?.resModel;
        if (resModel !== TARGET_MODEL) return items;

        const state = this.model?.root?.data?.state;
        if (state === undefined || state === null) return items;

        const isDraft = DRAFT_STATES.includes(state);

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
        } else {
            if (items.delete) {
                items.delete.isAvailable = () => false;
            }
        }

        return items;
    },

    async deleteRecord() {
        const resModel = this.model?.root?.resModel;
        if (resModel === TARGET_MODEL) {
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
