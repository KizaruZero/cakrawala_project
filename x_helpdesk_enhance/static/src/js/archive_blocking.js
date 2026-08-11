/** @odoo-module **/

/**
 * archive_blocking.js – helpdesk.ticket
 *
 * Gear / Action-menu behaviour (Odoo 19):
 *   - Lost/Archived (active = false) → Delete visible, Archive visible
 *   - New stage → Delete visible, Archive hidden
 *   - Cancelled stage → Delete visible, Archive visible
 *   - Solved stage → Delete hidden, Archive visible
 *   - In Progress / On Hold stages → Delete hidden, Archive hidden
 *
 * Custom deleteRecord always redirects to list view after deletion.
 */

import { patch } from "@web/core/utils/patch";
import { FormController } from "@web/views/form/form_controller";

const TARGET_MODEL = "helpdesk.ticket";

patch(FormController.prototype, {
    getStaticActionMenuItems() {
        const items = super.getStaticActionMenuItems(...arguments);

        const resModel = this.model?.root?.resModel;
        if (resModel !== TARGET_MODEL) return items;

        const active = this.model?.root?.data?.active !== false;
        const stageName = this.model?.root?.data?.stage_name;
        if (stageName === undefined || stageName === null) return items;

        if (!active) {
            if (items.delete) {
                items.delete.isAvailable = () => !this.model.root.isNew;
            }
        } else if (stageName === "New") {
            if (items.delete) {
                items.delete.isAvailable = () => !this.model.root.isNew;
            }
            if (items.archive) {
                items.archive.isAvailable = () => false;
            }
            if (items.unarchive) {
                items.unarchive.isAvailable = () => false;
            }
        } else if (stageName === "Cancelled") {
            if (items.delete) {
                items.delete.isAvailable = () => !this.model.root.isNew;
            }
        } else if (stageName === "Solved") {
            if (items.delete) {
                items.delete.isAvailable = () => false;
            }
        } else if (stageName === "In Progress" || stageName === "On Hold") {
            if (items.delete) {
                items.delete.isAvailable = () => false;
            }
            if (items.archive) {
                items.archive.isAvailable = () => false;
            }
            if (items.unarchive) {
                items.unarchive.isAvailable = () => false;
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
