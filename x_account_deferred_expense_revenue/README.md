# Deferred Expense and Revenue for Odoo 19

This addon restores deferred expense and deferred revenue automation as a separate installable module for Odoo 19.

## Main Flow

1. Create a Deferred Expense / Revenue Model from Accounting > Configuration.
2. Open a Chart of Accounts record:
   - Current Assets accounts can use Deferred Expense models.
   - Current Liabilities accounts can use Deferred Revenue models.
3. Set the Automation tab to:
   - No
   - Create in draft
   - Create and validate
4. Post a vendor bill or customer invoice using that account.
5. The module creates a deferred item and recognition board automatically.
6. On validate, past/current recognition entries are posted immediately at their accounting date. Future entries are scheduled with Auto-post At Date and posted by Odoo's native Accounting scheduler (`account.ir_cron_auto_post_draft_entry`).

## Accounting Logic

### Stop versus Write Off (19.0.1.0.10)

- **Write Off Deferred** is the former Stop Deferred behaviour: immediately
  recognize all remaining unrecognized periods in one journal, then set
  **Written Off**. Previously cancelled but unrecognized periods are included.
  Original Posted journals stay unchanged. Replaced Draft journals are now
  retained as Cancelled (`state=cancel`, `auto_post=no`) for audit instead of
  being deleted; their board rows point to the aggregate Posted journal.
- The new **Stop Deferred** sets **Stopped**, cancels only Draft recognition
  journals through native Odoo cancellation and disables their auto-posting.
  Posted journals, recognized value and residual value stay unchanged. No new
  journal is created and no remaining value is recognized. Legacy board rows
  without journals are also cancelled, not materialized into new journals.
- Recognition Board State follows the journal's real Draft/Posted/Cancelled
  state. Cancelling an individual journal from Journal Entries therefore also
  shows Cancelled on its board row. Upgrade migration repairs the stored state
  of historical already-cancelled journals, without rewriting journals, amounts,
  names, dates or historical parent states. Old Closed items are not guessed to
  be Written Off, and old names are not automatically renamed.
- Repeated Stop/Write Off requests do not generate duplicates. Lifecycle locks
  serialize these actions with recognition posting. Stopped, Written Off and
  Cancelled items cannot be revalidated/recomputed or their journals reset to
  Draft/reposted through the normal actions. Bulk Validate skips these statuses.
  Existing accounting rights and allowed-company checks remain in effect.
- Ordinary **Cancel** still refuses entries with Posted recognition. Its Draft
  journals are now cancelled and retained rather than deleted. Entries with
  recognition journals must be archived, not deleted; deleting a never-validated
  Draft/Cancelled item without journals remains possible.
- New product-based **Deferred Revenue** names use the product variant name
  plus the actual Analytic Account name(s), without RPC, quantities or rental
  periods from invoice descriptions. Internal product codes are omitted. If no
  analytic exists, only the product name is used. Existing expense/document-name
  behaviour, financial amounts and source links are unchanged.

Verification: **56 focused tests pass** (18 lifecycle, eight bulk validation,
30 Rental Order integration). Independent two-connection tests pass for Stop
racing posting and Stop racing Write Off. A real 19.0.1.0.9-to-19.0.1.0.10 upgrade
repairs a historical cancelled-board fixture while preserving all journal
dates/references/states/auto-post/write dates and deferred names/amounts/statuses.
The wider 297-test run has no runtime errors and only the seven known unrelated
Harga/Total PO Customer label assertions documented in the sale addon's README.
Tests use a disposable agent-owned database; staging is not changed.

### Bulk validation (19.0.1.0.9)

In Deferred Revenues and Deferred Expenses, select items and use **Action >
Validate**. Only Draft items are validated; Running, Closed and Cancelled items
are skipped and reported, never reopened. The action uses the existing validation
and recognition posting logic, including auto-post scheduling for future periods.
Accounting permissions and allowed-company scope remain enforced. Repeating a
bulk request does not create duplicate recognition moves. Upgrade this module
after deployment to install the list action.

Verification: all eight bulk-validation tests pass on an isolated temporary
database, covering both menus, native recognition posting/future scheduling,
repeat/mixed-state selections, permissions and allowed-company checks.

Invoice integrations can override `_get_deferred_source_lines()` to exclude
already-covered lines before account-model eligibility is evaluated. Ordinary
invoices without deferred-eligible lines do not query deferred metadata, and
recognition status uses the journal backlink (with a legacy fallback only when
the user has existing deferred-line read permission). No wider ACL is granted.

Deferred Expense recognition:

- Debit recognition expense account
- Credit deferred current asset account

Deferred Revenue recognition:

- Debit deferred current liability account
- Credit recognition revenue account

## Notes

- This module manages its own deferred records instead of modifying Odoo Enterprise asset internals.
- Refund reversal handling is intentionally not automated in this first version.
- Install and test on a staging database before production use.
