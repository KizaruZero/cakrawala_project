/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { DateTimeField } from "@web/views/fields/datetime/datetime_field";
import { formatDate } from "@web/views/fields/formatters";

patch(DateTimeField.prototype, {
    get field() {
        const fieldInfo = super.field;
        if (fieldInfo && this.props.showTime === false) {
            return { ...fieldInfo, type: "date" };
        }
        return fieldInfo;
    },
    getFormattedValue(valueIndex, numeric = this.props.numeric) {
        if (this.props.showTime === false) {
            const val = this.values[valueIndex];
            return val ? formatDate(val, { numeric }) : "";
        }
        return super.getFormattedValue(valueIndex, numeric);
    },
});
