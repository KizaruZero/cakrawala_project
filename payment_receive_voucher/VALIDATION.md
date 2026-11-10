# Validation — v1.4.9

- Native Odoo module suite: **22 tests pass, 0 failures/errors** in disposable
  database `codex_pv_report_20261110` (2026-11-10).
- New report regression verifies two table header columns, all five requested
  fields in the right cell, Total label, article/model metadata and retained
  UTF-8 meta after native PDF body extraction. Detailed report retains its
  original Bill Total label.
- Native QWeb/wkhtmltopdf PDFs rendered for Approved and Draft fixtures and
  visually inspected after Poppler PNG rendering: one A5 landscape page each,
  right-hand header aligned, no extra currency character, approval notices intact.
  Extracted total is Rp 151,792,000, matching the unchanged fixture bill total.
- No production/staging records changed. Upgrade `payment_receive_voucher` to
  **19.0.1.4.9** after deployment. QA fixture/database is disposable.

## Previous validation (v1.4.8)

- Python sources parsed with AST and XML files parsed for well-formedness.
- Manifest data paths checked against the module tree.
- ZIP root and archive integrity checked.
- Static validation only; no live Odoo 19 server was available.
- Print PV Summary Only uses its own A5 landscape paperformat and QWeb template without `web.external_layout`; Print PV Detail is unchanged.
