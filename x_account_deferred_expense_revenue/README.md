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
