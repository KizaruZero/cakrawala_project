/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { DateTimeField } from "@web/views/fields/datetime/datetime_field";

const { DateTime } = luxon;

patch(DateTimeField.prototype, {
    get field() {
        const fieldInfo = super.field;
        if (fieldInfo && this.props.showTime === false) {
            return { ...fieldInfo, type: "date" };
        }
        return fieldInfo;
    },
    getFormattedValue(valueIndex, numeric = this.props.numeric) {
        const val = this.values[valueIndex];
        if (!val) {
            return "";
        }

        if (numeric) {
            return super.getFormattedValue(valueIndex, numeric);
        }

        // Force year to appear for textual dates
        const { showSeconds, showTime } = this.props;
        const isDateOnly = this.field.type === "date" || showTime === false;

        if (isDateOnly) {
            const format = { ...DateTime.DATE_MED };
            return val.toLocaleString(format);
        } else {
            const showDate = !showTime || valueIndex !== 1 || !this.values[0] || !this.values[0].hasSame(val, "day");
            
            if (!showDate) {
                return super.getFormattedValue(valueIndex, numeric);
            }
            
            const format = { ...DateTime.DATETIME_MED };
            if (showSeconds) {
                format.second = "numeric";
            }
            return val.setZone(this.props.tz || "default").toLocaleString(format);
        }
    },
});
