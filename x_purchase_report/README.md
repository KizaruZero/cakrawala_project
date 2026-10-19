# PO printout - 19.0.1.0.2

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

## Item source: Input Order first, Products as fallback

Each Input Order row prints once, with its variant, description, quantity and
unit. It is not merged with a different Input Order row of the same variant.
Linked generated units supply the actual commercial values: weighted gross
unit price, total fixed/percentage discount, and tax-inclusive amount. No PO
amount or discount is recalculated or saved by printing.

When Input Order contains rows, all units must first be generated and must
match their source Input Order. An incomplete or mismatched Input Order still
receives a clear message; it is not silently replaced with Products.

When Input Order is absent or empty (including legacy/SPK POs), the printout
uses Products instead, one item row per purchase line in its original sequence.
Quantity, unit price, fixed/percentage discount and tax-inclusive amount come
directly from those lines. RPC references are still removed only on the
printout, and printing never changes the transaction. The mere presence of an
empty Input Order tab does not prevent this fallback.

If the PO has additional amounts outside the selected item rows, the totals
area discloses **Other PO Amounts**. For populated Input Order, extra unlinked
Products do not become item rows. The final Total is always the actual
`purchase.order.amount_total`.

Native Odoo tests verify grouping, discounts/taxes, preservation of stored
data, source priority and fallback, date/partner layout, and real PDF rendering.
For optional QA exports, set `PO_PDF_QA_DIR`; use wkhtmltopdf with patched Qt
for production-equivalent headers, footers and pagination.
