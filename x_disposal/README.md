# Disposal Bidding financial fields - 1.0.7

The existing technical field `disposal_sisa_laba_rugi_ditangguhkan` is retained
for export/API compatibility but its label is now **Laba Rugi Penjualan Kendaraan**.
Its new calculation is **Exclude PPN - Book Value**, not highest gross bid minus
book value. Generate first refreshes Exclude PPN with the existing selected-tax
calculation; Compute Selling Target also refreshes this sale gain/loss.

A separate read-only monetary field,
`disposal_leaseback_deferred_profit_loss`, is labelled **Sisa Laba Rugi
Ditangguhkan**. Its source is now:

`Vehicle -> latest Leaseback asset -> x_refinancing_move_id (Refinancing Entry)
-> account.deferred.entry.source_move_id (Deferred Items) -> residual_value`.

Only a real main asset with the exact same Vehicle and company is eligible.
If several Leaseback assets exist, latest means creation date, then ID; a newer
Draft/Running asset does not replace the Leaseback source. Archived history is
included. Residuals of non-cancelled Deferred Items on that exact Refinancing
Entry are summed. An old `deferred_expense_id` from another event is not used.
No eligible asset, Refinancing Entry or Deferred Item means zero. A fully
recognized zero remains zero; there is no fallback to the asset's original
`leaseback_deferred_pl_amount`, no sign conversion, and no name/plate guessing.
The actual deferred model name is `account.deferred.entry`.

Per user confirmation, downstream calculations use the deferred-residual
deferred amount, not the vehicle sale gain/loss:

- PHD = Book Value x 1.11 + Penalti Pelunasan - Sisa Laba Rugi Ditangguhkan.
- Selling Target Profit/Loss = Exclude PPN - Book Value - Penalti Pelunasan
  + Sisa Laba Rugi Ditangguhkan.
- Percentage = Selling Target Profit/Loss / Book Value x 100 (zero if Book Value
  is zero). The existing PHD 11% policy and selected Selling Target tax policy
  are unchanged.

Choosing/changing Vehicle fills the residual in the form immediately; clearing
Vehicle clears the amount. Create/write also apply this rule for API/imports.
Only this field is refreshed automatically on Vehicle selection; unrelated
financial snapshots are not silently recomputed. Compute Unit Information /
Generate PHD refreshes the residual together with PHD. The field also has its own Generate button. Compute
Selling Target / the existing gain/loss Generate button refreshes both financial
fields and Selling Target from the current deferred residual and selected tax.
These remain snapshots, not live writes whenever a recognition journal posts.
The separate Book Value/depreciation asset-resolution policy is unchanged.

No upgrade backfill rewrites existing financial snapshots, approvals, bids,
assets, sales orders, invoices or journals. Existing editable biddings should be
refreshed by reselecting Vehicle or using the calculation buttons. Approved biddings retain the existing
write protection. The PDF labels and Disposal Reporting columns distinguish the
two amounts. Deploy and upgrade **x_disposal 1.0.7**; the existing
**x_disposal_reporting 1.2** columns use the same stored field.

## 1.0.7 QA - 2026-11-13

**60 native Disposal tests passed, 0 failures/errors**, in a disposable no-demo
database with an Indonesian chart. Coverage includes real form onchanges before
saving, Vehicle switch/clear, multi-create/API writes, exact Vehicle/company and
Leaseback selection, latest Leaseback vs newer Draft assets, exact refinancing
event vs stale deferred links, multiple/cancelled items, missing sources and a
fully recognized zero. Residuals use actual posted recognition journals, not
assigned compute caches. PHD/Selling Target, sale gain/loss, form/report labels,
Approved snapshot protection and existing disposal invoice/payment/BASTK flows
also passed. No assets or recognition journals are modified by the new lookup.

No upgrade backfill or staging changes were performed. QA business transactions
were rolled back and the temporary database was removed after verification.
Logs: `/tmp/cakrawala-disposal-residual.Qq9z5xFU/tests-final.log`.

## Previous 1.0.6 QA - 2026-11-12

**49 native Disposal tests passed, 0 failures/errors**, after upgrading both
Disposal modules in a disposable no-demo database with an Indonesian chart.
Coverage includes net-vs-gross selling price, separate asset-sourced gains/losses,
positive/negative/zero amounts, stale inputs, PHD and Selling Target without
double counting, zero book value, real leaseback reference values, native form
and report fields, Approved write protection, stock delivery, invoice/payment
and BASTK flows. The actual native PDF was rendered and visually checked: one
A4 page, separate labels/amounts, no clipping or overlapping.

The additional asset-module regression run completed 65 tests: 64 passed and
one existing archive-lifecycle case errored. A Leaseback asset has the custom
state `leaseback`, whereas native `account.asset._check_active` only accepts
`close` when archiving (`TestOneAssetPerVehicle.test_archived_asset_frees_the_vehicle`).
This is unrelated to Disposal calculations and was not changed in production
code. Old asset-test fixtures were completed with mandatory asset models and
explicit fleet models; only test setup changed in that module.

No sample business records were committed. The disposable database was removed;
logs and the sample PDF remain at `/tmp/cakrawala-disposal-pnl.usYm7VFy/`.
