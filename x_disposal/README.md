# Disposal Bidding financial fields - 1.0.6

The existing technical field `disposal_sisa_laba_rugi_ditangguhkan` is retained
for export/API compatibility but its label is now **Laba Rugi Penjualan Kendaraan**.
Its new calculation is **Exclude PPN - Book Value**, not highest gross bid minus
book value. Generate first refreshes Exclude PPN with the existing selected-tax
calculation; Compute Selling Target also refreshes this sale gain/loss.

A separate read-only monetary field,
`disposal_leaseback_deferred_profit_loss`, is labelled **Sisa Laba Rugi
Ditangguhkan**. It copies `account.asset.leaseback_deferred_pl_amount` (Leaseback
Profit/Loss) from the vehicle's uniquely resolved asset. Positive, zero and
negative amounts are copied literally, not a deferred-entry amortization residual
or Sell/Disposal Gain/Loss. No asset means zero; ambiguous asset links retain the
existing explicit error rather than guessing. `x_account_asset_leaseback` is now
an explicit dependency so this source field is guaranteed available.

Per user confirmation, downstream calculations now use the new asset-sourced
deferred amount, not the vehicle sale gain/loss:

- PHD = Book Value x 1.11 + Penalti Pelunasan - Sisa Laba Rugi Ditangguhkan.
- Selling Target Profit/Loss = Exclude PPN - Book Value - Penalti Pelunasan
  + Sisa Laba Rugi Ditangguhkan.
- Percentage = Selling Target Profit/Loss / Book Value x 100 (zero if Book Value
  is zero). The existing PHD 11% policy and selected Selling Target tax policy
  are unchanged.

Compute Unit Information / Generate PHD refreshes the asset-sourced amount
together with PHD. The new field also has its own Generate button. Compute
Selling Target / the existing gain/loss Generate button refreshes both financial
fields and Selling Target from the current asset and selected tax, avoiding stale
tax bases or deferred values. These are calculation snapshots, following the
existing explicit button workflow, not live edits to an approved document.

No upgrade backfill rewrites existing financial snapshots, approvals, bids,
assets, sales orders, invoices or journals. Existing editable biddings should be
refreshed with the calculation buttons. Approved biddings retain the existing
write protection. The PDF labels and Disposal Reporting columns distinguish the
two amounts. Deploy and upgrade **x_disposal 1.0.6** and **x_disposal_reporting
1.2** (plus its new dependency if not already installed).

## QA - 2026-11-12

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
