# Payment & Receive Voucher — v1.4.7

Technical module: `payment_receive_voucher`  
Odoo manifest version: `19.0.1.4.7` · Target: Odoo 19 Enterprise · LGPL-3

## v1.4.7 changes
- A bill with an active Payment Voucher must be paid through that voucher's Pay button. Partial payments keep using the same voucher for the outstanding balance; a replacement voucher is blocked until the earlier voucher is Cancelled or Rejected.

## v1.4.4 changes
- The Create Payment Voucher popup only confirms the selected bills and outstanding amounts. Select the required Payment Voucher Type on the voucher form before submitting. It is editable while Draft and readonly after submission.

## Install
1. Back up the database and test on a staging copy first.
2. Extract `payment_receive_voucher_v1.4.7.zip`. Place its
   `payment_receive_voucher` folder in your custom addons path.
3. Restart Odoo, enable developer mode, update the Apps list, remove the Apps-only
   search filter, and install **Payment & Receive Voucher**. For an existing v1.x database,
   upgrade the module instead of reinstalling it. Existing approval configurations default
   **Allow Edit Amount for Partial Payment** to off after the upgrade.
   Existing voucher-to-document history uses the same relation table, so no history migration is needed.
   CLI alternative: `odoo-bin -d DATABASE -u payment_receive_voucher --stop-after-init`.
4. Assign the appropriate Vouchers role in Settings → Users. Assign normal Accounting
   permissions separately; voucher roles do not grant permission to pay or edit invoices.
5. A **Voucher Manager** creates company-specific entries at Accounting → Configuration →
   Payment Voucher Types, then sets up the routes under Voucher Approval Configuration.
   Assign approvers their role and company first.

## Approval configuration
- Before creating Payment Vouchers, create company-specific Payment Voucher Types
  (for example, Bank Transfer, Cash or Cheque). Each Payment Voucher records one type;
  Receive Vouchers do not use this field.
- An **active** configuration makes approval mandatory for all vendor bills (`payment`)
  or all customer invoices (`receive`) in that company, including existing unpaid documents.
- No active configuration means standard payment flow. Archiving is an explicit way to
  disable enforcement; it is restricted to Voucher Managers. Do not archive as a workaround.
- A Payment Voucher may still be created without an active configuration and is marked
  Approved automatically on Submit. Create Receive Voucher is hidden and blocked unless the
  company has an active Receive Voucher configuration. Any active configuration with no
  approval layers auto-approves on Submit.
- One configuration per company, voucher direction and Payment Voucher Type, including archived
  ones; reuse/unarchive that record. Payment Voucher configs may leave the type empty as a general
  fallback. An exact type config takes precedence; Receive Voucher configs keep the type empty.
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
- **Allow Edit Amount for Partial Payment** is disabled by default. When enabled, the Pay
  wizard for an approved voucher allows a lower amount. When disabled, the amount remains at
  Odoo's default due amount and custom lower amounts are rejected server-side.
- **Require Same Vendor / Customer** is enabled by default. When enabled, all documents
  selected for one voucher must have the same partner. When disabled, multiple partners
  are allowed in one voucher; company and currency must still match. The native payment
  wizard separates the resulting payments by partner as required by Odoo.

## Use
1. From a posted Vendor Bill form, **Create Payment Voucher** remains visible. Creation is blocked while any linked voucher is active, including after a partial payment; use that same voucher to settle the balance, or cancel/reject it before making a replacement. Pay from the bill is blocked while an active Payment Voucher applies; use the voucher's **Pay** button. The Vendor Bills list toolbar follows the same creation rule. On a posted Customer Invoice, **Create Receive Voucher** is shown only when an active Receive Voucher configuration exists for the company; the form button and invoice list action both confirm before creating anything. Partially paid invoices can also receive a new voucher for the remaining balance.
2. All selected documents must share the same company and currency and have a positive
   outstanding balance. They must also share the same partner when the configuration requires it.
   Drafts, credit notes, blocked, paid and in-payment documents are excluded. Partially paid
   documents are eligible for their remaining balance.
3. On the Payment Voucher form, choose the mandatory Payment Voucher Type (the create popup no longer includes this selector; type stays editable only while Draft). Review vendor bank details, **Summary**, flattened **Item Details**, notes and
   **Approval History**. Analytic Distribution shows analytic account names only, without percentages.
   Amounts/details are snapshotted at creation and refreshed once on submission.
   The source document's Voucher Approval tab lists all linked vouchers. A new voucher for a
   partially paid document becomes the latest authorization while prior vouchers remain listed.
4. Submit. The current approver sees separate green **Approve** and red **Reject** buttons.
   Each opens a small popup containing only the voucher and Notes. Rejection requires a reason.
   Delegated actions record both original and actual approvers.
5. After approval, use standard Odoo **Pay**. Use the form gear → Print menu to choose **Print PV Detail** or **Print PV Summary Only**. These options appear on Payment Vouchers only. Both show analytic account names, Bank Account Number, Bank Name, and Account Holder Name in the header; the detailed printout also includes Bill Details. Approval itself creates no payment,
   journal entry or reconciliation. Partial payment amount editing is controlled by the configuration checkbox above.
   If the configuration enables the voucher Pay button, the same native wizard can be opened
   directly from the approved Payment or Receive Voucher form. The PDF print actions need wkhtmltopdf 0.12.6 available to Odoo; without it Odoo falls back to HTML preview.
6. Settlement is displayed separately as Unpaid / Partially Paid or In Payment / Paid,
   derived from the source documents. Authorization status stays Approved.

Draft, Waiting and Approved vouchers reserve unpaid documents. A partially paid document may be linked to a new voucher for its remaining balance; all earlier vouchers remain in its Voucher Approval history. Cancel a voucher to release its source documents for correction or for a new voucher; the cancelled voucher retains its snapshots and history. Creators can cancel Draft vouchers; Voucher Managers can cancel submitted vouchers.

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
  is outside the v1.4.3 workflow and requires staging review before use.
- Credit notes/receipts cannot get their own vouchers. Matching a credit note against a
  governed invoice requires that invoice's approval. Financial changes to approved paid
  documents require a standard credit note/new invoice rather than editing the original.
- Read access is company-wide, not limited to a voucher's assigned approvers. Creator self-approval
  is allowed if explicitly configured. Chatter is supplementary; structured history is the audit trail.
- No attachments requirement, email/activity reminders, batch splitting,
  partial authorization allocation, or editable approval routes in this initial release.
- Bill Details shows product lines; sections/notes are omitted. Analytic distribution is saved
  as readable snapshot text. Summary includes full invoice totals and remaining amounts.
- Numbers look like `PV/2026/10/0001` and `RV/2026/10/0001`; counters are global per type,
  increase continuously (no monthly reset), may contain gaps and grow beyond four digits.
- The Payment Voucher button appears on Vendor Bill forms and the Bill list toolbar; the Receive
  Voucher button appears on the Invoice list toolbar.
  Backend validation still rejects credit notes, receipts, drafts and mixed document types.
  Menus remain visible even if a type has no active configuration.
- Payment Voucher PDFs have a grouped product summary table, separate tax rows and a full
  Bill Details table. Identical product names are combined in the summary.

## Staging tests
Run the bundled Odoo tests on a disposable Odoo 19 Enterprise database with Accounting installed:
`odoo-bin -d TEST_DATABASE -i payment_receive_voucher --test-enable --test-tags /payment_receive_voucher --stop-after-init`
Also exercise multi-company restrictions, two concurrent voucher requests, partial/grouped
payments, foreign currency, credit-note matching, bank matching, and paid voucher cancellation.
See `VALIDATION.md` for offline checks and `tests/test_voucher.py` for executable scenarios.

## Versioning
Release ZIPs are immutable. v1.4.3 keeps the `payment_receive_voucher` technical module name,
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














