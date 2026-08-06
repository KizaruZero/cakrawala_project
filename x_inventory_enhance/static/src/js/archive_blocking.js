/** @odoo-module **/

/**
 * archive_blocking.js – stock.picking, stock.picking.batch, stock.scrap
 *
 * Gear / Action-menu behaviour (Odoo 19):
 *
 * stock.picking:
 *   - draft → Delete visible, Archive hidden
 *   - cancel → Delete visible, Archive visible
 *   - done → Delete hidden, Archive visible
 *   - waiting, confirmed, assigned → Delete hidden, Archive hidden
 *
 * stock.picking.batch:
 *   - draft → Delete visible, Archive hidden
 *   - cancel → Delete visible, Archive visible
 *   - done → Delete hidden, Archive visible
 *   - in_progress → Delete hidden, Archive hidden
 *
 * stock.scrap:
 *   - draft → Delete visible, Archive hidden
 *   - done → Delete hidden, Archive visible
 */

import { patch } from "@web/core/utils/patch";
import { FormController } from "@web/views/form/form_controller";

patch(FormController.prototype, {
    getStaticActionMenuItems() {
        const items = super.getStaticActionMenuItems(...arguments);

        const resModel = this.model?.root?.resModel;
        if (resModel !== "stock.picking" && resModel !== "stock.picking.batch" && resModel !== "stock.scrap") {
            return items;
        }

        const active = this.model?.root?.data?.active !== false;
        const state = this.model?.root?.data?.state;
        if (state === undefined || state === null) return items;

        if (resModel === "stock.picking") {
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
            } else if (state === "cancel") {
                if (items.delete) {
                    items.delete.isAvailable = () => !this.model.root.isNew;
                }
            } else if (state === "done") {
                if (items.delete) {
                    items.delete.isAvailable = () => false;
                }
            } else {
                // waiting, confirmed, assigned
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
        } else if (resModel === "stock.picking.batch") {
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
            } else if (state === "cancel") {
                if (items.delete) {
                    items.delete.isAvailable = () => !this.model.root.isNew;
                }
            } else if (state === "done") {
                if (items.delete) {
                    items.delete.isAvailable = () => false;
                }
            } else if (state === "in_progress") {
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
        } else if (resModel === "stock.scrap") {
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
            } else if (state === "done") {
                if (items.delete) {
                    items.delete.isAvailable = () => false;
                }
            }
        }

        return items;
    },

    async deleteRecord() {
        const resModel = this.model?.root?.resModel;
        if (resModel === "stock.picking" || resModel === "stock.picking.batch" || resModel === "stock.scrap") {
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
