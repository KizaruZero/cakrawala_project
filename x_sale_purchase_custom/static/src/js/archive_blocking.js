/** @odoo-module **/

/**
 * archive_blocking.js – sale.order & account.move
 *
 * Gear / Action-menu behaviour (Odoo 19):
 *
 * sale.order:
 *   - draft state → Delete visible, Archive hidden
 *   - sent, sale, done states → Delete hidden, Archive visible
 *   - cancel state → Delete visible, Archive visible
 *
 * account.move:
 *   - draft state → Delete visible, Archive hidden
 *   - posted state → Delete hidden, Archive visible
 *   - cancel state → Delete visible, Archive visible
 *
 * Custom deleteRecord redirects to list view after deletion.
 */

import { patch } from "@web/core/utils/patch";
import { FormController } from "@web/views/form/form_controller";

patch(FormController.prototype, {
    getStaticActionMenuItems() {
        const items = super.getStaticActionMenuItems(...arguments);

        const resModel = this.model?.root?.resModel;
        if (resModel !== "sale.order" && resModel !== "account.move") return items;

        const state = this.model?.root?.data?.state;
        if (state === undefined || state === null) return items;

        if (resModel === "sale.order") {
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
            } else if (state === "sent" || state === "sale" || state === "done") {
                if (items.delete) {
                    items.delete.isAvailable = () => false;
                }
            } else if (state === "cancel") {
                if (items.delete) {
                    items.delete.isAvailable = () => !this.model.root.isNew;
                }
            }
        } else if (resModel === "account.move") {
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
            } else if (state === "posted") {
                if (items.delete) {
                    items.delete.isAvailable = () => false;
                }
            } else if (state === "cancel") {
                if (items.delete) {
                    items.delete.isAvailable = () => !this.model.root.isNew;
                }
            }
        }

        return items;
    },

    async deleteRecord() {
        const resModel = this.model?.root?.resModel;
        if (resModel === "sale.order" || resModel === "account.move") {
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
