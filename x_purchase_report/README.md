# PO printout - 19.0.1.0.1

Upgrade `x_purchase_report` after deploying. The report now explicitly depends
on `x_purchase_request_create_po` (Input Order) and
`purchase_order_lines_discount` (fixed-discount calculation).

## Layout and labels

- **Expected Arrival Date** prints the PO header's `date_planned`, using the
  viewer's timezone, not the first/last actual receipt date.
- Leasing Partner is next to that date and prints its name only.
- The decorative bubble/curve beside the company logo is removed.
- Payment Terms on the printout reads **Two weeks after delivery unit**.
  This does not change `payment_term_id`, bill due dates, or payment calculations.
- Generated RPC references are removed from printed item descriptions only;
  saved Input Order/Products descriptions and RPC links remain unchanged.

## Input Order is the only source of item rows

Each Input Order row prints once, with its variant, description, quantity and
unit. It is not merged with a different Input Order row of the same variant.
Linked generated units supply the actual commercial values: weighted gross
unit price, total fixed/percentage discount, and tax-inclusive amount. No PO
amount or discount is recalculated or saved by printing.

All units must first be generated and must match their source Input Order.
Orders with no Input Order (including legacy/SPK POs) receive a clear message;
there is deliberately **no fallback to Products**, as requested.

If the PO has additional amounts outside those linked Input Order units, the
totals area discloses **Other PO Amounts**, without adding Products item rows.
The final Total is always the actual `purchase.order.amount_total`.

Native Odoo tests verify grouping, discounts/taxes, preservation of stored
data, the strict source rules, date/partner layout, and real PDF rendering.
For optional QA exports, set `PO_PDF_QA_DIR`; use wkhtmltopdf with patched Qt
for production-equivalent headers, footers and pagination.
