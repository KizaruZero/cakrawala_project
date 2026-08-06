/** @odoo-module **/

import { FormController } from "@web/views/form/form_controller";
import { patch } from "@web/core/utils/patch";

patch(FormController.prototype, {
    get actionMenuItems() {
        const menuItems = super.actionMenuItems;
        const record = this.model.root;
        if (record.resModel === "fleet.spk") {
            const state = record.data.state;
            menuItems.action = menuItems.action?.filter((item) => {
                if (item.key === "delete" && state !== "new") return false;
                if (item.key === "archive" && state === "new") return false;
                return true;
            });
        }
        return menuItems;
    },
});