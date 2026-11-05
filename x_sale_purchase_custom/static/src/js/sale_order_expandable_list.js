import { useState } from "@odoo/owl";
import { patch } from "@web/core/utils/patch";
import { useService } from "@web/core/utils/hooks";
import { ListRenderer } from "@web/views/list/list_renderer";

patch(ListRenderer.prototype, {
    setup() {
        super.setup(...arguments);
        if (this.isSaleOrderExpandableList) {
            this.orm = useService("orm");
            this.soExpandState = useState({
                expandedIds: {},
                linesByOrderId: {},
                loadingByOrderId: {},
            });
        }
    },

    get isSaleOrderExpandableList() {
        return (
            this.props.list?.resModel === "sale.order" &&
            !this.props.nestedKeyOptionalFieldsData &&
            !this.env.inDialog
        );
    },

    isSaleOrderExpanded(record) {
        return Boolean(
            this.isSaleOrderExpandableList &&
            record?.resId &&
            this.soExpandState?.expandedIds[record.resId]
        );
    },

    getSaleOrderLines(record) {
        return (record?.resId && this.soExpandState?.linesByOrderId[record.resId]) || [];
    },

    isSaleOrderLinesLoading(record) {
        return Boolean(record?.resId && this.soExpandState?.loadingByOrderId[record.resId]);
    },

    async toggleSaleOrderExpand(record, ev) {
        if (ev) {
            ev.stopPropagation();
            ev.preventDefault();
        }
        const orderId = record?.resId;
        if (!orderId || !this.soExpandState) {
            return;
        }
        const nextExpanded = !this.soExpandState.expandedIds[orderId];
        this.soExpandState.expandedIds[orderId] = nextExpanded;
        if (nextExpanded && !(orderId in this.soExpandState.linesByOrderId)) {
            this.soExpandState.loadingByOrderId[orderId] = true;
            try {
                const lines = await this.orm.call(
                    "sale.order",
                    "get_expandable_order_lines",
                    [orderId]
                );
                this.soExpandState.linesByOrderId[orderId] = lines || [];
            } finally {
                this.soExpandState.loadingByOrderId[orderId] = false;
            }
        }
    },

    async onCellClicked(record, column, ev, newWindow) {
        if (ev?.target?.closest?.(".o_so_expand_btn")) {
            return;
        }
        return super.onCellClicked(...arguments);
    },
});

