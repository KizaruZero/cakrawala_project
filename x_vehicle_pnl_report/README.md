# Laporan Laba Rugi Kendaraan - 19.0.1.0.6

The vehicle-selection wizard now includes **all Fleet statuses** (Leased,
Non-Leased, Inactive, other/custom or no status), including **archived vehicles**.
The explicit operational-status test and Odoo's implicit `active_test` filter are
removed from the direct-link, reverse-link and plate-match selection paths.
Archived analytic accounts with historical transactions also remain eligible.

Per user confirmation, **an existing Analytic Item is still required**. This is
the original `account.analytic.line.account_id` transaction criterion, not all
vehicles or all accounts merely created in master data. Any-date/any-account-type
eligibility, plate/analytic name/code search, preserved checkbox selections and
the existing report date cutoff and financial formulas are unchanged.

Default wizard loading and search use the same candidate resolver. Analytic
transaction IDs use native ORM grouping instead of unscoped raw SQL; selected
companies and read rules apply. Empty/restricted results are not retried with
sudo to show another company's or otherwise restricted vehicles. No vehicle is
reactivated or reclassified and no journal/analytic transaction is rewritten.

Deploy and upgrade **x_vehicle_pnl_report 19.0.1.0.6**, then reopen the wizard.
No data migration, regenerated journal or staging-data edit is needed. The
existing report calculations and Running-leasing/asset summary selection rules
are not changed by this patch.
