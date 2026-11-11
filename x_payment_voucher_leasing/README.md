# Leasing Payment Voucher — 19.0.1.0.1

New Payment Voucher Leasing recipients come from the PO's **Leasing Partner**,
through `account.loan.line.leasing_partner_id` (x_leasing_amortization 19.0.1.0.21).
Voucher header, recipient summary, detail recipient snapshots and all payment
journal header/debit/credit partners use that same source. The technical detail
field `vendor_id` remains a stored snapshot, labelled **Vendor / Leasing Partner**
so older dealer-based vouchers retain their original data and meaning.

**Require Same Leasing Partner** compares the financing companies, not vehicle
suppliers: different dealers with one lessor may share a voucher; different
lessors require the configuration to allow it. The existing one-journal-per-loan
flow is unchanged. Missing PO Leasing Partner blocks creation/payment; there is
no silent fallback to the dealer or the editable loan-header `bank_id` snapshot.

The approved recipient is not silently redirected. Submit, approval and payment
validate the stored recipient against the PO Leasing Partner. If it changed,
cancel and recreate the voucher for a new approval. Unpaid legacy vouchers may
continue only when their stored recipient still matches the PO Leasing Partner;
otherwise recreate them. Paid vouchers and posted journals are not rewritten.
Recipient/source snapshots cannot be edited or replaced after submission.

Payment locks the voucher, its source POs and leasing schedules, rechecks source
links, recipients and existing payment/settlement links, then creates/posts the
same principal/interest amounts to the same accounts and selected bank journal.
An error rolls back the complete payment, including a multi-loan batch.

No installment formula, date, analytic distribution or financial amount is
recomputed. PO Vendor, regular non-voucher payment, accrued-interest journals
and early-settlement Vendor Bills retain their existing partner source. Accounting
must review any historic dealer-based balances/accruals separately; this patch
does not reclassify or reconcile them automatically.

Deploy and upgrade **both** x_leasing_amortization (19.0.1.0.21) and
x_payment_voucher_leasing (19.0.1.0.1). No staging transactions are edited here.

Verification (2026-11-11): **255 native Odoo tests pass, 0 failures/errors** on
a disposable database after upgrading both modules: all 232 leasing regressions
and 23 voucher partner tests. Coverage includes real approval by a configured
approver, posted header/item partners, unchanged debit/credit amounts and bank
accounts, multi-dealer/single-lessor and multi-lessor policies, missing/changed
PO partners, legacy recipient mismatch, immutable submitted snapshots (including
context-default creation), reset/reapproval, posted-history preservation,
duplicate/settlement protection, atomic rollback, ADDM/ADDB and unchanged accrual
source. No production/staging journal or historical balance is migrated.
