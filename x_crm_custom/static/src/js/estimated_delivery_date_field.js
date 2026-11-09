/** @odoo-module **/

import { registry } from "@web/core/registry";
import { DateTimeField, dateField } from "@web/views/fields/datetime/datetime_field";

export function formatEstimatedDeliveryDate(value) {
    // Luxon is immutable: changing the display locale never changes the date.
    return value ? value.setLocale("en").toFormat("dd, LLL yyyy") : "";
}

export class EstimatedDeliveryDateField extends DateTimeField {
    getFormattedValue(valueIndex, numeric = this.props.numeric) {
        // Keep the native numeric tooltip/editor and all date-picker behavior.
        if (numeric) {
            return super.getFormattedValue(valueIndex, numeric);
        }
        return formatEstimatedDeliveryDate(this.values[valueIndex]);
    }
}

registry.category("fields").add("crm_estimated_delivery_date", {
    ...dateField,
    component: EstimatedDeliveryDateField,
});
