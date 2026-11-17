# Skip Approval — 19.0.1.5.3

Deploy and upgrade `payment_receive_voucher` to **19.0.1.5.3**.

Customer Invoice / Vendor Bill headers now include **Skip Approval**. Accounting
users (`account.group_account_invoice`) who have native write access to the
document can change it on Draft/Posted documents. It defaults to false, is not
copied to new invoices/credit notes, and changes are tracked in native chatter.
It cannot be enabled on Journal Entries, refunds or receipts; empty/false
payloads on those documents remain harmless.

When enabled:

- Use the document's normal **Pay** button without Payment/Receive Voucher
  approval. This applies to wizard creation and final payment execution, invoice
  line payment actions, and the payment/reconciliation guards, not just the UI.
- Both Create Payment Voucher and Create Receive Voucher are hidden on the form.
  New voucher creation is also rejected through batch/list actions, the create
  wizard, and direct voucher creation. Mixed voucher selections must exclude
  flagged documents instead of silently ignoring them.
- Existing Draft/Waiting/Approved vouchers may remain linked, as requested.
  Their approval state, snapshots and history are not modified or auto-approved.
  The current residual/settlement information continues following real payments.
- The old voucher's partial-payment permission does not restrict a skipped
  document. Odoo's native payment registration and amount calculations are used;
  the requested amount must not exceed the refreshed outstanding balance.
  A stale open wizard must be reopened after another payment reduces the balance.

When disabled, the existing voucher approval and voucher-route requirements
apply again, including rechecks on an already-open wizard. A skip flag on one
document never bypasses approval for another document in the same payment batch.

This is an approval exception, not a general edit/unlock flag. Native Accounting
ACLs, company/period/posting/payment validations remain in force. Financial
fields of a document with an active voucher remain frozen under the existing
voucher rules. No source quantity, price, tax, account, analytic or accounting
amount is recalculated by ticking the flag. No existing vouchers, invoices,
payments or journals are migrated or generated on upgrade.

Implementation is isolated in `models/skip_approval.py` and
`views/skip_approval_views.xml`; existing payment guards still handle every
unflagged document. Payment operations and flag changes share invoice row locks.

Verification (2026-11-12): **46 native Odoo tests passed, 0 failures/errors**
(23 existing voucher regressions + 23 Skip Approval regressions). Tests cover
actual Accounting-user payments for both invoice types, existing vouchers in
Draft/Waiting/Approved states, original snapshot/history preservation, current
residual updates, stale-wizard overpayment prevention, flag-off rechecks, mixed
payment batches, copy/reversal defaults, native Draft-payment parity, access
rights, native chatter tracking, and voucher creation through form/list/wizard
and direct model paths. Tests ran in an owned disposable local database; no
staging data was changed.
