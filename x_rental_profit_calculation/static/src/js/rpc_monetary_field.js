/** @odoo-module **/

import { registry } from "@web/core/registry";
import { formatMonetary } from "@web/views/fields/formatters";
import { MonetaryField, monetaryField } from "@web/views/fields/monetary/monetary_field";

/**
 * Readonly monetary display with the currency symbol pinned to the left and
 * the amount pinned to the right, so figures stay comparable in RPC tables
 * that are otherwise left-aligned. Supports an optional `digits` override so
 * a specific view (e.g. the Full Tenor profitability table) can display
 * fewer/more decimals than the currency's default, without touching the
 * stored value or any backend computation.
 */
export class RpcMonetaryField extends MonetaryField {
    static template = "x_rental_profit_calculation.RpcMonetaryField";
    static props = {
        ...MonetaryField.props,
        digits: { type: Array, optional: true },
    };

    get currencyDigits() {
        return this.props.digits || super.currencyDigits;
    }

    get currencySymbolText() {
        return this.currency ? this.currency.symbol : "";
    }

    get formattedValueOnly() {
        return formatMonetary(this.value, {
            digits: this.currencyDigits,
            currencyId: this.currencyId,
            noSymbol: true,
            trailingZeros: this.props.trailingZeros,
        });
    }
}

export const rpcMonetaryField = {
    ...monetaryField,
    component: RpcMonetaryField,
    extractProps: (fieldInfo) => {
        const props = monetaryField.extractProps(fieldInfo);
        const { attrs, options } = fieldInfo;
        let digits;
        if (attrs.digits) {
            digits = JSON.parse(attrs.digits);
        } else if (options.digits) {
            digits = options.digits;
        }
        return { ...props, digits };
    },
};

registry.category("fields").add("rpc_monetary", rpcMonetaryField);
