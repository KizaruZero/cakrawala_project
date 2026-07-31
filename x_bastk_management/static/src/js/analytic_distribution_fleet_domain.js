/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { AnalyticDistribution } from "@analytic/components/analytic_distribution/analytic_distribution";

/**
 * Restrict the Analytic Distribution account dropdown for fleet products.
 *
 * The native widget builds each plan's account many2one domain as
 * [["root_plan_id", "=", planId], <company filter>], with no product filter.
 * For sale order lines whose product is a fleet product (is_vehicle = true), we
 * AND an extra ["id", "in", analytic_account_domain_ids] clause so only the
 * analytic accounts of vehicles belonging to that product are selectable.
 *
 * The two helper fields (is_vehicle, analytic_account_domain_ids) are provided
 * invisibly by the sale order view. When they are absent (any other model that
 * uses this widget), the patch is a no-op and falls back to native behaviour.
 */
patch(AnalyticDistribution.prototype, {
    recordProps(line) {
        const props = super.recordProps(line);
        const record = this.props.record;
        if (!record || !record.data || !record.data.is_vehicle) {
            return props;
        }
        const allowed = record.data.analytic_account_domain_ids;
        const allowedIds = allowed && allowed.currentIds ? allowed.currentIds : [];
        for (const fieldName in props.fields) {
            const field = props.fields[fieldName];
            if (field && field.relation === "account.analytic.account" && field.domain) {
                field.domain = ["&", ["id", "in", allowedIds], ...field.domain];
            }
        }
        return props;
    },
});
