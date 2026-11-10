# Purchase fixed discount and vendor bill deductions — 19.0.1.2.3

Vendor bill product lines now offer **Biaya Lain-Lain**
(`account.move.line.other_cost_deduction`), a monetary deduction in the bill
currency. It is subtracted **once per line**, after the existing percentage or
fixed discount, from the tax-excluded subtotal. Quantity does not multiply this
deduction. Native taxes, line totals, payable/residual and journal balances use
the reduced base. For included taxes, Odoo first extracts the original DPP and
then subtracts the deduction, so DPP falls by the exact amount entered.

Example: DPP after discount 100,000,000 minus deduction 5,000,000 gives DPP
95,000,000; PPN/PPh are recomputed from that base. This is a price reduction,
not a separate expense line/account. Original unit price, fixed discount and
percentage inputs remain unchanged. Vendor credit notes preserve the deduction
for standard reversal consistency; customer invoices cannot use it.

The field appears in the bill lines list and mobile line form. It is editable
only in Draft, enforced server-side too. Deduction must be finite, nonnegative,
on a product line with positive quantity, and cannot exceed DPP after discount.
Zero/unset preserves the old calculation. Existing documents are not backfilled
or explicitly recalculated. Receipt valuation/PO pricing formulas are unchanged.

Deploy and upgrade **purchase_order_lines_discount** to **19.0.1.2.3**. No
staging/operational database is modified by this patch.

Verification (2026-11-10): **12 native Odoo tests pass, 0 failures/errors** in a
disposable database. Coverage includes quantity/fixed/percentage discounts,
amount-only edits and clearing, included/excluded taxes and combined PPN/PPh,
native form onchange/save, multi-line atomic rejection, foreign currency,
balanced posting, standard credit-note reversal and unchanged zero-cost cases.
