# Changelog

## v1.3.1 — 2026-10-01
- Fixed the Odoo 19 upgrade error caused by unsupported `confirm-title` and
  `confirm-label` attributes in the server-side Vendor Bill list view.
- Kept the standard confirmation prompt before creating a Payment Voucher.
- Kept the list-controller fallback that displays Create Receive Voucher on the
  Customer Invoices selection toolbar, including its confirmation dialog.

## v1.3.0 — 2026-10-01
- Rendered Create Receive Voucher through Odoo's list controller so it remains visible when
  Enterprise or custom modules replace the Customer Invoice XML list view.
- Added confirmation dialogs to Create Payment Voucher and Create Receive Voucher before
  any voucher is created.
- Kept the working Vendor Bill button on its existing XML path.

## v1.2.2 — 2026-10-01
- Fixed Create Receive Voucher visibility for Customer Invoice actions that identify the
  screen through `search_default_out_invoice` instead of only `default_move_type`.
- Added the equivalent fallback for Vendor Bills and shortened the customer button label to
  **Create Receive Voucher**.

## v1.2.1 — 2026-10-01
- Added **Require Same Vendor / Customer** to each company/type approval configuration.
- The option defaults to True. When disabled, one voucher may contain multiple partners while
  company and currency remain mandatory matches.
- Mixed-partner vouchers show `Multiple Partners (N)` in the header and preserve each partner
  name in the Bills / Summary snapshot. Native payment registration continues to batch by partner.

## v1.2.0 — 2026-10-01
- Added **Show Pay Button on Voucher** to each company/type approval configuration.
- When enabled, approved Payment and Receive Voucher forms show Pay and open Odoo's native
  `account.payment.register` wizard for their outstanding source documents.
- The option defaults to False and is enforced in the backend as well as the form view.

## v1.1.2 — 2026-10-01
- Removed the Config, Approved By, Approved At and Approved Remarks summary block from
  the Approval History tab so the Approval Route table appears immediately.
- Updated empty-state guidance to reference the list toolbar buttons.

## v1.1.1 — 2026-10-01
- Fixed the Customer Invoice toolbar button by inheriting Odoo's shared invoice list view.
- Both create buttons now use the active list context: Payment Voucher on Vendor Bills and
  Receive Payment Voucher on Customer Invoices.
- Technical module name remains `payment_receive_voucher`; upgrade v1.1.0 normally.

## v1.1.0 — 2026-10-01
- Split Approve and Reject into green/red form buttons with a notes-only decision popup.
- Added Reset Bills to cancel a mistaken voucher and release source documents while retaining audit data.
- Moved voucher creation from the Action menu to selection toolbar buttons dedicated to
  Vendor Bills and Customer Invoices.
- Kept the technical module name `payment_receive_voucher` for normal upgrade from v1.0.1.

## v1.0.1 — 2026-10-01
- Removed the previous brand from the ZIP folder, module name, model and field prefixes,
  XML references, labels, tests and documentation.
- Archive folder / technical module: `payment_receive_voucher`.
- Approval and payment behavior unchanged. Prior release archives preserved.
- Fresh installation release; existing v1.0.0 databases require a separate migration.

## v1.0.0 — 2026-10-01
- Initial Payment Voucher / Receive Voucher implementation.
