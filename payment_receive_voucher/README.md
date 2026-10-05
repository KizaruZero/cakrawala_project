# Payment & Receive Voucher — v1.3.1

Technical module: `payment_receive_voucher`  
Odoo manifest version: `19.0.1.3.1` · Target: Odoo 19 Enterprise · LGPL-3

## Install
1. Back up the database and test on a staging copy first.
2. Extract `payment_receive_voucher_v1.3.1.zip`. Place its
   `payment_receive_voucher` folder in your custom addons path.
3. Restart Odoo, enable developer mode, update the Apps list, remove the Apps-only
   search filter, and install **Payment & Receive Voucher**.
   CLI alternative: `odoo-bin -d DATABASE -i payment_receive_voucher --stop-after-init`.
4. Assign the appropriate Vouchers role in Settings → Users. Assign normal Accounting
   permissions separately; voucher roles do not grant permission to pay or edit invoices.
5. An administrator with **Voucher Manager + Accounting Administrator** opens
   Accounting → Configuration → Voucher Approval Configuration. Create one configuration
   for each company/type you want to enforce. Assign approvers their role and company first.

## Approval configuration
- An **active** configuration makes approval mandatory for all vendor bills (`payment`)
  or all customer invoices (`receive`) in that company, including existing unpaid documents.
- No active configuration means standard payment flow. Archiving is an explicit way to
  disable enforcement; it is restricted to Voucher Managers. Do not archive as a workaround.
- One configuration per company/type, including archived ones; reuse/unarchive that record.
- Layers have a unique positive number and an inclusive minimum threshold in company currency.
  Every qualifying layer is required, in layer order. Example: thresholds 0 / 100,000 / 500,000
  mean a 700,000 voucher requires all three approvals. A zero-threshold layer is required at submission.
- Foreign-currency totals convert using the configured Odoo rate on the voucher date.
- Delegate authorization is additional to the original approver, inclusive of both dates,
  evaluated using the server's UTC date. Approvers/delegates must be active internal Voucher
  Approvers with access to the company. No manager override of approval order exists.
- The route and delegation dates are frozen on submission. Later configuration changes
  apply to new submissions. Cancel and recreate to change an uncompleted route.
- **Show Pay Button on Voucher** is disabled by default. When enabled, approved vouchers
  display a Pay button that opens Odoo's standard payment registration wizard. Changing
  the boolean affects existing vouchers that use the configuration.
- **Require Same Vendor / Customer** is enabled by default. When enabled, all documents
  selected for one voucher must have the same partner. When disabled, multiple partners
  are allowed in one voucher; company and currency must still match. The native payment
  wizard separates the resulting payments by partner as required by Odoo.

## Use
1. From the Vendor Bills list, select one or more rows and click the visible
   **Create Payment Voucher** toolbar button. On the Customer Invoices list, use
   **Create Receive Voucher**. Both commands show a confirmation dialog before creating
   anything. These commands are no longer placed in the Action menu. The Receive button
   is rendered through the Odoo list controller so it also works with Enterprise/custom
   invoice list views that replace the standard XML view.
2. All selected documents must share the same company and currency and have a positive
   outstanding balance. They must also share the same partner when the configuration requires it.
   Drafts, credit notes, blocked, paid and in-payment documents are excluded. Partially paid
   documents are eligible for their remaining balance.
3. Review **Bills / Summary**, flattened **Bill Details**, notes and **Approval History**.
   Amounts/details are snapshotted at creation and refreshed once on submission.
4. Submit. The current approver sees separate green **Approve** and red **Reject** buttons.
   Each opens a small popup containing only the voucher and Notes. Rejection requires a reason.
   Delegated actions record both original and actual approvers.
5. After all layers approve, use standard Odoo **Pay**. Approval itself creates no payment,
   journal entry or reconciliation. Partial payments/installments remain standard Odoo;
   authorization covers the remaining documents, not a separate payment amount allocation.
   If the configuration enables the voucher Pay button, the same native wizard can be opened
   directly from the approved Payment or Receive Voucher form.
6. Settlement is displayed separately as Unpaid / Partially Paid or In Payment / Paid,
   derived from the source documents. Authorization status stays Approved.

Draft, Waiting and Approved vouchers reserve their documents. **Reset Bills** cancels the
voucher and releases its source documents for correction or a new voucher while preserving
the old snapshots and history. A creator may reset Draft/Waiting vouchers; a Manager may also
reset Approved vouchers that have no payment activity or changed outstanding balance.
Reject/Cancel permits a new voucher; old snapshots/history remain. Only a creator or Manager can edit/submit draft notes.
Creators can cancel their drafts; Managers can cancel uncompleted submitted/approved vouchers.
Approved vouchers with partial/in-payment/paid activity or changed balances cannot be cancelled.
No voucher deletion, reset-to-draft, or duplication is offered. A bill shows its active/latest voucher.

## Security and backend coverage
- Voucher User: read company vouchers, create from accessible documents, manage own drafts.
- Voucher Approver: User rights plus decisions on the current assigned layer or valid delegation.
- Voucher Manager: configuration management and cancellation rights; still must be assigned
  to a layer to approve. Normal Accounting permissions remain independent.
- Global company rules cover voucher/configuration/audit models. Accounting invoice users
  may read voucher references and snapshots but cannot operate the workflow without a voucher role.
- Checks cover bill/invoice Pay, journal-item Pay, wizard defaults and execution,
  invoice-linked payments, and creation of partial reconciliations (including bank matching
  and credit-note settlement). Source accounting fields/lines cannot be changed while linked
  to an active voucher. Workflow/audit fields reject direct ORM writes; no context bypass is provided.
- Document rows are locked during creation, approval/cancel and payment validation to prevent
  concurrent active vouchers or decisions. Standard transaction rollback protects failed operations.

## Current limitations / validation status
- No live Odoo/PostgreSQL server was available. Python/XML, manifest/data references and
  deterministic policy tests were checked offline. Included Odoo integration tests have
  **not been executed**; installation and runtime compatibility must be verified in staging.
- Uses public Odoo 19 Accounting hooks. Enterprise bank reconciliation, localization,
  cash-basis taxes, exchange differences, EDI and other custom addons need staging regression tests.
- Standalone payments with no invoice link are allowed; applying/linking them to a governed
  invoice requires approval. This module is invoice authorization, not a bank disbursement control.
- If unreconciliation increases a document's outstanding amount above its approval snapshot,
  payment is blocked pending a new approval. Reallocation of earlier payments on active vouchers
  is outside the v1.3.1 workflow and requires staging review before use.
- Credit notes/receipts cannot get their own vouchers. Matching a credit note against a
  governed invoice requires that invoice's approval. Financial changes to approved paid
  documents require a standard credit note/new invoice rather than editing the original.
- Read access is company-wide, not limited to a voucher's assigned approvers. Creator self-approval
  is allowed if explicitly configured. Chatter is supplementary; structured history is the audit trail.
- No printable voucher PDF, attachments requirement, email/activity reminders, batch splitting,
  partial authorization allocation, or editable approval routes in this initial release.
- Bill Details shows product lines; sections/notes are omitted. Analytic distribution is saved
  as its original ID/percentage mapping. Summary includes full invoice totals and remaining amounts.
- Numbers look like `PV/2026/10/0001` and `RV/2026/10/0001`; counters are global per type,
  increase continuously (no monthly reset), may contain gaps and grow beyond four digits.
- The create buttons live in the Bill and Invoice list headers and appear with row selection.
  Backend validation still rejects credit notes, receipts, drafts and mixed document types.
  Menus remain visible even if a type has no active configuration.

## Staging tests
Run the bundled Odoo tests on a disposable Odoo 19 Enterprise database with Accounting installed:
`odoo-bin -d TEST_DATABASE -i payment_receive_voucher --test-enable --test-tags /payment_receive_voucher --stop-after-init`
Also exercise multi-company restrictions, two concurrent voucher requests, partial/grouped
payments, foreign currency, credit-note matching, bank matching, and paid voucher cancellation.
See `VALIDATION.md` for offline checks and `tests/test_voucher.py` for executable scenarios.

## Versioning
Release ZIPs are immutable. v1.3.0 keeps the `payment_receive_voucher` technical module name,
so an existing v1.x installation can be upgraded normally after a database backup.
Future releases will use new versioned ZIPs without replacing prior archives.

## Source compatibility references
Checked against public Odoo 19.0 source on 2026-10-01:
- https://github.com/odoo/odoo/blob/19.0/addons/account/models/account_move.py
- https://github.com/odoo/odoo/blob/19.0/addons/account/models/account_move_line.py
- https://github.com/odoo/odoo/blob/19.0/addons/account/models/account_payment.py
- https://github.com/odoo/odoo/blob/19.0/addons/account/wizard/account_payment_register.py
- https://github.com/odoo/odoo/blob/19.0/addons/account/models/account_partial_reconcile.py
- https://github.com/odoo/odoo/blob/19.0/addons/account/views/account_menuitem.xml
- https://github.com/odoo/odoo/blob/19.0/odoo/addons/base/models/res_groups.py
