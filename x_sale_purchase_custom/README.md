# Customer invoice printout (0.36)

After deploying the source, upgrade `x_sale_purchase_custom`.

## Existing stamp-duty product

In **Accounting > Configuration > Settings > Rental Invoices**, select the
existing **Biaya Materai** sales service product in **Stamp Duty - IDR 10,000**.
Accounting must check its income account and customer taxes first. The addon
does not create a product or CoA and applies the usual fiscal-position mapping.
Leaving this company-specific setting empty disables the automatic charge.

Each **new IDR invoice created by Billing Engine** receives one actual
Rp10,000 invoice line, using that product's account and taxes. The PDF shows
the charge separately from DPP and includes it in Total and Terbilang.
Generate again or append a late-delivered unit: no duplicate charge.
Existing draft or posted invoices are not charged retroactively. This is not
a print-only surcharge, nor an automatic fee on vendor bills/manual invoices.

## Print data

The customer-invoice PDF uses the company's saved logo, the customer's invoice
payment terms and native tax totals. It prints BCA 1685656789 and the approved
payment instructions and signature. Vendor bills retain their native layout.

New Billing Engine descriptions store the real registration (not the FN asset
number), with rental dates in `dd-mm-yyyy`. For old rental invoices, a report
helper removes generated RPC references/plate labels and formats dates without
rewriting posted invoice lines. Actual plate resolution uses the related fleet
vehicle or vehicle analytic account, respecting access/company rules; if no
registration is available it displays `-`, never an invented plate.

## Verification

Native Odoo tests cover actual accounting totals, withholding/PPN, idempotent
generation, preserving old invoices, and real one-page/multipage PDF rendering.
Optional test-only PDF exports use `INVOICE_PDF_QA_DIR`.
For production-equivalent multipage pagination, use wkhtmltopdf with patched Qt;
the distribution's unpatched Qt build can split table rows despite print CSS.
