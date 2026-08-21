/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { patch } from "@web/core/utils/patch";
import { useService } from "@web/core/utils/hooks";
import { roundDecimals } from "@web/core/utils/numbers";
import { AnalyticDistribution } from "@analytic/components/analytic_distribution/analytic_distribution";

/**
 * Beri tahu user begitu editor analytic distribution ditutup, tanpa menunggu
 * record disimpan.
 *
 * Penolakan sebenarnya tetap ada di constraint server
 * (`analytic.mixin._check_analytic_distribution_total`); ini murni umpan balik
 * lebih awal. Sengaja tidak memblokir penutupan editor supaya user tidak
 * terjebak di dalam dropdown saat ingin membatalkan isian.
 */
patch(AnalyticDistribution.prototype, {
    setup() {
        super.setup(...arguments);
        this.distributionNotification = useService("notification");
    },

    closeAnalyticEditor() {
        super.closeAnalyticEditor(...arguments);
        this.warnIfDistributionTotalInvalid();
    },

    warnIfDistributionTotalInvalid() {
        if (this.props.readonly || this.props.multi_edit) {
            return;
        }
        const entries = Object.entries(this.dataToJson()).filter(
            ([key]) => key !== "__update__"
        );
        // Analytic distribution kosong tetap boleh.
        if (!entries.length) {
            return;
        }
        const digits = this.decimalPrecision.digits[1];
        const total = roundDecimals(
            entries.reduce((sum, [, percentage]) => sum + percentage, 0),
            digits
        );
        if (total === 100) {
            return;
        }
        const gap = roundDecimals(Math.abs(100 - total), digits);
        this.distributionNotification.add(
            total < 100
                ? _t("Total analytic distribution saat ini %(total)s%% — kurang %(gap)s%%.", {
                      total: total,
                      gap: gap,
                  })
                : _t("Total analytic distribution saat ini %(total)s%% — kelebihan %(gap)s%%.", {
                      total: total,
                      gap: gap,
                  }),
            {
                title: _t("Analytic distribution harus 100%"),
                type: "danger",
            }
        );
    },
});
