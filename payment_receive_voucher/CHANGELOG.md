## v1.4.8 — 2026-11-09
- Updated Print PV Summary Only: adds the red, bold italic Draft/fully-approved status notice; removes the standard report header and footer; uses a compact A5 landscape page with the summary table stretched across the available width.

## v1.4.7 — 2026-11-03
- Added a server-side blocker preventing Pay amount from exceeding the current outstanding invoice amount. It runs when the wizard is created/edited and again before payment creation.

## v1.4.6 — 2026-11-03`r`n- Fixed Pay from voucher by carrying the approved voucher reference in the returned payment wizard action and validating it when the wizard opens and creates payments.`r`n`r`n## v1.4.5 — 2026-11-03
- Blocked payment registration from the Vendor Bill when an active Payment Voucher authorizes it; continue partial settlement from that same voucher's Pay button.
- Blocked creating a replacement Payment Voucher while any linked voucher is active, including partially paid bills. The warning identifies the active voucher(s) and directs users to continue payment there or cancel/reject it before replacement.
- Passed voucher authorization context into Odoo's standard payment registration flow and retained checks against the approved voucher snapshot and current outstanding balance.

## v1.4.4 — 2026-11-03
- Removed Payment Voucher Type from the create confirmation wizard; the popup now only confirms the selected bills and outstanding amounts.
- Payment Voucher Type must be selected on the voucher form before submission, remains editable in Draft, and locks after submission.
- Kept server-side checks so a draft without a type cannot be submitted, including when there is only one active type.

## v1.4.3 — 2026-10-30
- Fixed partial amount editing in voucher Pay: when the configuration permits it, the standard wizard enables grouped payment mode for multiple same-batch bills/invoices, which Odoo requires to apply an edited aggregate amount.
- Preserved native Odoo editability and grouping behavior for payments without an active voucher configuration.
- Added backend validation to reject edited amounts when the wizard cannot apply them to its payment batch.

## v1.4.2 — 2026-10-30
- Renamed voucher form tabs to **Summary** and **Item Details**.
- Partially paid documents can receive a new voucher for the remaining balance, even while earlier vouchers remain active.
- Added a complete linked-voucher history list to the source Bill/Invoice Voucher Approval tab; all previous voucher records remain linked.
- Kept the latest voucher as the payment authorization pointer and restore the previous active voucher if the newest draft/waiting voucher is cancelled.
- Prevented a historical voucher's Pay button from opening payment registration after a newer voucher supersedes it.

## v1.4.1 — 2026-10-30
- Fixed the Pay wizard amount field so the partial-payment permission is derived from every linked approved voucher's own approval configuration and has final view priority.
- Hide Create Receive Voucher on invoice forms and the invoice list unless the company has an active Receive Voucher configuration; the backend action enforces the same rule.

## v1.4.0 — 2026-10-30
- Added **Create Receive Voucher** to posted Customer Invoice forms with a confirmation prompt.
- Submitting without an active approval configuration, or with an active configuration containing no layers, now auto-approves the voucher.
- Added **Allow Edit Amount for Partial Payment** to approval configuration. It controls amount editing in the approved voucher's standard Pay wizard, with server-side checks when disabled.
- Payment enforcement now considers active approval configurations only; no active config leaves standard Odoo invoice payments available.

## v1.3.12 — 2026-10-30
- Added a subtle inset horizontal divider above the Payment Voucher title in both printouts to separate the company logo/address header from voucher content.

## v1.3.11 — 2026-10-30
- Moved Analytic into the left header column directly below Currency, keeping five header items on each side in both printouts.

## v1.3.10 — 2026-10-30
- Matched the Summary table font to the standard Bill Details table font in both printouts while retaining the compact table width.

## v1.3.9 — 2026-10-30
- Corrected the Summary table sizing: it now has an explicit 640px width instead of filling the whole report page.
- Fixed column widths to 330px Item, 100px Quantity, and 210px Amount in both printouts.

## v1.3.8 — 2026-10-30
- Resized the Summary table columns in both printouts: Item 60%, Quantity 15%, Amount 25%.
- Reduced cell padding and kept Quantity and Amount values on one line so the columns fit their contents more closely.

## v1.3.7 — 2026-10-30
- Moved bank details to the right column in both Payment Voucher printouts.
- Bank fields now appear in the requested order: Bank Name, Bank Account Number, Account Holder Name.

## v1.3.6 — 2026-10-30
- Kept Create Payment Voucher visible on every posted Vendor Bill, including bills with a prior voucher link.
- Added a blocking message for bills linked to Draft, Waiting Approval, or Approved vouchers; bills with no voucher, Cancelled, or Rejected vouchers remain eligible.
- Switched bank information to active bank account records attached to the bill vendor (with commercial-partner fallback) and added Account Holder Name.

## v1.3.5 — 2026-10-30
- Fixed the vendor heading in both voucher PDF layouts so long vendor names wrap within the page.
- Added read-only Bank Account Number and Bank Name to the Payment Voucher header and both printouts, using the bank account selected automatically on the source bill(s).

## v1.3.4 — 2026-10-29
- Moved the two Payment Voucher reports from form header buttons into the gear → Print menu.
- Added Print PV Detail and Print PV Summary Only report actions, bound to Payment Voucher forms and hidden on Receive Vouchers.

## v1.3.3 — 2026-10-29
- Removed the Reset Bills button; use Cancel to release documents while preserving voucher audit snapshots.
- Payment Voucher Type can be changed while Draft and locks after submission.
- Analytic Distribution snapshots now show unique analytic account names only, with no percentages; upgrade migration cleans existing snapshots.
- Added separate Detailed and Summary-only Payment Voucher PDF reports. Both show comma-separated analytic names in the header.
- Report table headings are bold, centered, and use a subtle shaded background.

# Changelog

## v1.3.2 — 2026-10-29
- Added company-specific Payment Voucher Type master data and a selector on the Payment Voucher form/creation popup.
- Added Payment Voucher Type as an approval configuration scope, with a general fallback for existing configurations.
- Added the Create Payment Voucher button to Vendor Bill forms and a confirmation/type-selection popup.
- Replaced analytic distribution IDs with readable names and percentages, including migration of existing snapshots.
- Added a Payment Voucher PDF with grouped product summary rows, separate tax rows, and full Bill Details.
- Added an upgrade migration to expand approval-configuration uniqueness.

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












