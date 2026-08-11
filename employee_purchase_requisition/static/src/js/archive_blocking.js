/** @odoo-module **/

/**
 * archive_blocking.js – employee.purchase.requisition
 *
 * Gear / Action-menu behaviour (Odoo 19):
 *   - draft state → Delete visible, Archive hidden
 *   - waiting_approval state → Delete hidden, Archive hidden
 *   - approved, purchase_order_created states → Delete hidden, Archive visible
 *   - rejected state → Delete visible, Archive visible
 *
 * Custom deleteRecord always redirects to list view after deletion.
 */

import { patch } from "@web/core/utils/patch";
import { FormController } from "@web/views/form/form_controller";

const TARGET_MODEL = "employee.purchase.requisition";

patch(FormController.prototype, {
    getStaticActionMenuItems() {
        const items = super.getStaticActionMenuItems(...arguments);

        const resModel = this.model?.root?.resModel;
        if (resModel !== TARGET_MODEL) return items;

        const state = this.model?.root?.data?.state;
        if (state === undefined || state === null) return items;

        if (state === "draft") {
            if (items.delete) {
                items.delete.isAvailable = () => !this.model.root.isNew;
            }
            if (items.archive) {
                items.archive.isAvailable = () => false;
            }
            if (items.unarchive) {
                items.unarchive.isAvailable = () => false;
            }
        } else if (state === "waiting_approval") {
            if (items.delete) {
                items.delete.isAvailable = () => false;
            }
            if (items.archive) {
                items.archive.isAvailable = () => false;
            }
            if (items.unarchive) {
                items.unarchive.isAvailable = () => false;
            }
        } else if (state === "approved" || state === "purchase_order_created") {
            if (items.delete) {
                items.delete.isAvailable = () => false;
            }
            // archive and unarchive default to true (visible)
        } else if (state === "rejected") {
            if (items.delete) {
                items.delete.isAvailable = () => !this.model.root.isNew;
            }
            // archive and unarchive default to true (visible)
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
