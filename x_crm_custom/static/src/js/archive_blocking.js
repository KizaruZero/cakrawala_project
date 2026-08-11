/** @odoo-module **/

/**
 * archive_blocking.js – crm.lead & utm.campaign
 *
 * Gear / Action-menu behaviour (Odoo 19):
 *
 * crm.lead:
 *   - Lost (active = false) → Delete visible, Archive visible
 *   - New (active = true) → Delete visible, Archive hidden
 *   - Qualified, Won stages (active = true) → Delete hidden, Archive visible
 *   - Other stages (Proposition, etc. active = true) → Delete hidden, Archive hidden
 *
 * utm.campaign:
 *   - Inactive (active = false) → Delete visible, Archive visible
 *   - Schedule, New stages (active = true) → Delete visible, Archive hidden
 *   - Sent stage (active = true) → Delete hidden, Archive visible
 *   - Design stage (active = true) → Delete hidden, Archive hidden
 *
 * Custom deleteRecord always redirects to list view after deletion.
 */

import { patch } from "@web/core/utils/patch";
import { FormController } from "@web/views/form/form_controller";

patch(FormController.prototype, {
    getStaticActionMenuItems() {
        const items = super.getStaticActionMenuItems(...arguments);

        const resModel = this.model?.root?.resModel;
        if (resModel !== "crm.lead" && resModel !== "utm.campaign") return items;

        const active = this.model?.root?.data?.active !== false;
        const stageName = this.model?.root?.data?.stage_name;

        if (resModel === "crm.lead") {
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
            } else if (stageName === "Qualified" || stageName === "Won") {
                if (items.delete) {
                    items.delete.isAvailable = () => false;
                }
            } else {
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
        } else if (resModel === "utm.campaign") {
            if (!active) {
                if (items.delete) {
                    items.delete.isAvailable = () => !this.model.root.isNew;
                }
            } else if (stageName === "Schedule" || stageName === "New") {
                if (items.delete) {
                    items.delete.isAvailable = () => !this.model.root.isNew;
                }
                if (items.archive) {
                    items.archive.isAvailable = () => false;
                }
                if (items.unarchive) {
                    items.unarchive.isAvailable = () => false;
                }
            } else if (stageName === "Sent") {
                if (items.delete) {
                    items.delete.isAvailable = () => false;
                }
            } else if (stageName === "Design") {
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
        }

        return items;
    },

    async deleteRecord() {
        const resModel = this.model?.root?.resModel;
        if (resModel === "crm.lead" || resModel === "utm.campaign") {
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
