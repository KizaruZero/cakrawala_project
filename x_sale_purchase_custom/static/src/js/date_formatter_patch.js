/** @odoo-module **/

import { registry } from "@web/core/registry";
import { formatDate as originalFormatDate, formatDateTime as originalFormatDateTime } from "@web/views/fields/formatters";

const { DateTime } = luxon;

const formattersRegistry = registry.category("formatters");

/**
 * Patch the default Odoo 'date' formatter.
 * By default, Odoo's toLocaleDateString drops the year if it matches the current year.
 * We override it here to explicitly format the date using DateTime.DATE_MED which guarantees the year is shown.
 * This ensures list views (which use the registry directly) will display the year.
 */
formattersRegistry.add("date", function formatDateCustom(value, options = {}) {
    if (options.numeric) {
        return originalFormatDate(value, options);
    } else {
        if (!value) {
            return "";
        }
        const format = { ...DateTime.DATE_MED };
        return value.toLocaleString(format);
    }
}, { force: true });

/**
 * Patch the default Odoo 'datetime' formatter.
 */
formattersRegistry.add("datetime", function formatDateTimeCustom(value, options = {}) {
    if (options.numeric) {
        return originalFormatDateTime(value, options);
    } else {
        if (!value) {
            return "";
        }
        const format = { ...DateTime.DATETIME_MED };
        if (options.showSeconds) {
            format.second = "numeric";
        }
        return value.setZone(options.tz || "default").toLocaleString(format);
    }
}, { force: true });
