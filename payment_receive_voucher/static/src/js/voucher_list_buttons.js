/** @odoo-module **/

import { user } from "@web/core/user";
import { patch } from "@web/core/utils/patch";
import { ListController } from "@web/views/list/list_controller";
import { onWillStart } from "@odoo/owl";

patch(ListController.prototype, {
    setup() {
        super.setup(...arguments);
        this.prvHasVoucherUser = false;
        onWillStart(async () => {
            this.prvHasVoucherUser = await user.hasGroup(
                "payment_receive_voucher.group_voucher_user"
            );
        });
    },

    get prvCanShowReceiveVoucherButton() {
        if (!this.prvHasVoucherUser || this.props.resModel !== "account.move") {
            return false;
        }
        const selection = this.model.root.selection;
        if (!selection.length) {
            return false;
        }
        const context = this.model.root.context || {};
        const fallbackType = context.default_move_type ||
            (context.search_default_out_invoice ? "out_invoice" : false);
        return selection.every(
            (record) => (record.data.move_type || fallbackType) === "out_invoice"
        );
    },

    get prvReceiveVoucherClickParams() {
        return {
            type: "object",
            name: "action_create_receive_voucher",
            confirm: "Create a Receive Voucher for the selected customer invoices? Please verify the documents and outstanding amounts before proceeding.",
            "confirm-title": "Create Receive Voucher?",
            "confirm-label": "Proceed",
        };
    },
});
