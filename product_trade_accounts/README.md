# Product Trade Accounts (Odoo 19)

Version: 19.0.1.0.3

Adds optional company-dependent Customer Receivable Account and Vendor Payable Account fields to the product Accounting tab. Invoice payment-term lines are split by account according to invoice-line totals; unset product accounts fall back to the partner account. Fiscal-position account mapping is applied. Same-date AR/AP lines are treated as one due installment in the Pay wizard. Odoo creates account-specific payments from the matching lines so reconciliation remains on each account.

## Install

Copy the `product_trade_accounts` folder into an Odoo addons path, restart Odoo, update the Apps list, and install **Product Trade Receivable and Payable Accounts**.

## Configure

As an Accounting Manager, edit a product and set either optional account on the Accounting tab. Receivable accounts must have type Receivable; payable accounts must have type Payable. Values vary by company.

## Behavior

Customer invoices and credit notes use the configured receivable account. Vendor bills and refunds use the configured payable account. Each invoice's total (including taxes) is allocated among accounts in proportion to invoice line totals. An unset product account uses the normal partner property account. Fiscal positions map the selected account using Odoo's standard account mapping.

## Changelog

- 19.0.1.0.3 — Remove unsupported `account.account.deprecated` domain filter for Odoo 19.
- 19.0.1.0.1 — Fix Odoo 19 Accounting tab inheritance and add account-based payment-term splits.`r`n- 19.0.1.0.0 — Initial product account fields.

## Validation note

This package was not run against your local Odoo installation. Verify installation and a draft/post/payment cycle on a test database before production use.



