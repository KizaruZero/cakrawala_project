/** @odoo-module **/

import { QtyAtDatePopover, QtyAtDateWidget, qtyAtDateWidget } from "@sale_stock/widgets/qty_at_date_widget";
import { registry } from "@web/core/registry";
import { roundPrecision } from "@web/core/utils/numbers";

/** Many2one values in list/form records are { id, display_name } (Odoo 19+), not always [id, name]. */
function m2oId(raw) {
    if (raw == null || raw === false) {
        return undefined;
    }
    if (typeof raw === "number") {
        return raw;
    }
    if (Array.isArray(raw)) {
        return raw[0];
    }
    if (typeof raw === "object" && "id" in raw) {
        return raw.id;
    }
    return undefined;
}

/**
 * Same look/feel as sale quotations (sale_stock.QtyAtDate) but uses
 * forecast_product_id (product variant on spk.product.line).
 */
export class SpkQtyAtDatePopover extends QtyAtDatePopover {
    openForecast() {
        const data = this.props.record.data;
        const pid = m2oId(data.forecast_product_id);
        if (!pid) {
            return;
        }
        this.actionService.doAction("stock.stock_forecasted_product_product_action", {
            additionalContext: {
                active_model: "product.product",
                active_id: pid,
                warehouse_id: m2oId(data.warehouse_id),
                move_to_match_ids: [],
                sale_line_to_match_id: false,
            },
        });
    }
}

export class SpkQtyAtDateWidget extends QtyAtDateWidget {
    static components = { Popover: SpkQtyAtDatePopover };

    async calcDataForDisplay() {
        const { data } = this.props.record;
        let lineUom;
        const lineUomId = m2oId(data.product_uom_id);
        if (lineUomId) {
            lineUom = (await this.orm.read("uom.uom", [lineUomId], ["factor", "rounding"]))[0];
        }
        let lineProduct;
        const fpId = m2oId(data.forecast_product_id);
        if (fpId) {
            lineProduct = await this.orm.searchRead("product.product", [["id", "=", fpId]], ["uom_id"]);
        }
        let productUom;
        const pUomId = m2oId(lineProduct?.[0]?.uom_id);
        if (pUomId) {
            productUom = (await this.orm.searchRead("uom.uom", [["id", "=", pUomId]], ["factor", "name"]))[0];
        }
        if (lineUom && productUom) {
            this.calcData.product_uom_virtual_available_at_date = roundPrecision(
                data.virtual_available_at_date * (lineUom.factor / productUom.factor),
                1
            );
            this.calcData.product_uom_free_qty_today = roundPrecision(
                data.free_qty_today * (lineUom.factor / productUom.factor),
                1
            );
            this.calcData.product_uom_name = productUom.name;
        }
    }
}

export const spkQtyAtDateWidget = {
    component: SpkQtyAtDateWidget,
    fieldDependencies: [
        ...qtyAtDateWidget.fieldDependencies.filter((d) => d.name !== "move_ids"),
        { name: "forecast_product_id", type: "many2one" },
        { name: "product_uom_id", type: "many2one" },
        { name: "state", type: "selection" },
    ],
};

registry.category("view_widgets").add("spk_qty_at_date_widget", spkQtyAtDateWidget);
