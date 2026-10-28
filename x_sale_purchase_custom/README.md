# Rental invoices and Return ET (0.52)

After deploying the source, upgrade `x_sale_purchase_custom`.

## Two independent invoice print formats

- **Invoice PDF** and **PDF without Payment** retain their native Odoo actions,
  templates and normal company paperformat selection. Standard Print/Preview/Send
  defaults are not rebound to the custom report. Other installed native/localized
  report extensions remain in place.
- **Custom Print Out** is an additional Print-menu action, available for customer
  invoices and customer credit notes. It retains the existing Cakrawala custom
  layout, grouping, detail appendix, unit registration handling, DPP/fee breakdown,
  Indonesian amount words, stored terms, signature, dates and payment display.
  It uses its own paperformat and filename prefix `Custom -`.
- All three historical global view XML IDs are converted to **primary** (private)
  variants, so they no longer extend the shared invoice, wrapper or external
  layout. The custom action explicitly calls its private document/layout. No
  global context flag is required to switch the standard report.
- On upgrade to 0.52, only native report actions still pointing to this module's
  old custom paperformat are reset to normal company defaults. A different
  paperformat chosen separately by Accounting is preserved. The migration does
  not change invoices, amounts, customers, taxes, journals, payments or PDFs.
- Printing either format reads the same invoice and its existing amounts; it
  does not regenerate Billing Engine transactions or alter accounting data.
  The custom action neither reuses nor overwrites the native cached invoice PDF.
  Archived/generated invoice attachments are preserved. If an old Print/Send
  workflow downloads an already stored PDF, use the desired Print-menu action to
  render a fresh copy; historical PDFs are not silently replaced during upgrade.

Verification: 67 invoice report tests passed (0 failures/errors) on an isolated
database, including a real upgrade from 0.51 to 0.52, standard/custom HTML and
PDF rendering, old custom-layout regressions, company paperformat preservation,
and cached-attachment/accounting immutability. Baseline 0.51 one- and two-page
custom PDFs retain identical normalized text/page counts after the split (only
the test SO sequence reference is normalized for comparison).

## Invoice PDF: single-unit detail / multi-unit appendix

For customer rental invoices and rental credit notes (not ET penalty invoices):

- A Rental Order containing one vehicle prints the actual **Invoice Lines** in
  the main table, without product grouping. Multi-unit orders retain their
  existing reconciled main summary and add **LAMPIRAN RINCIAN INVOICE**, starting
  on a new page. Only the current invoice's charged lines are detailed, never
  unbilled units/months from the entire contract.
- Vehicle quantity comes from rentable Input Order quantities when present,
  otherwise generated rentable Order Lines. For invoices without linked orders,
  use invoice rental quantities excluding stamp/other fees. Billing months and
  fee quantities do not turn a one-vehicle contract into a multi-vehicle order.
  Legacy products/source lines with missing `rent_ok`/`is_rental` flags are also
  recognized by their actual non-fee Invoice Line product links. A zero source
  quantity falls back to the invoiced rental quantity, not the one-unit layout.
  Distinct invoice registrations also provide a lower bound on vehicle count;
  an understated legacy Input Order cannot turn 12 actual plates into one unit.
  No product/master or historical source flag is changed by printing.
- Detail columns are No., No Polisi, Tipe/Product, Periode Sewa, Bulan Ke,
  Harga Sewa, PPN, PPh and Total. The snapshot `x_billing_month` is printed as-is.
  Rental periods retain the English `MMM d, yyyy` date format. Real plate numbers
  retain the existing historical-invoice/analytic fallback and FN identifiers
  are not printed as registrations. Sections, notes and source order are kept.
- The appendix replaces the old List Nopol; plates are not repeated in the
  multi-unit main summary. Ordinary non-rental invoices keep their earlier
  grouping/list behaviour. Vendor bills keep the native report.
- The appendix header shows only the invoice number and its source SO reference,
  without the customer/contact name. Its existing header spacing is retained to
  preserve long-table page boundaries. Customer name and address on the main
  invoice page remain unchanged. This affects only printing, not the invoice's
  customer or accounting data.
- PPN/PPh columns show **amounts**, not rates. Tax amounts come from Odoo's
  native rounded tax details, including grouped/included taxes, global rounding
  and stored manual tax amounts. PPh is displayed positive for a deduction:
  `Total rincian unit = net rental amount + PPN - PPh + other taxes`. An additional tax
  column is shown only if other tax types exist; they are not relabelled as PPN.
- Harga Sewa uses the actual untaxed line subtotal after discount (quantity is
  disclosed when not 1). Stamp duty and other Biaya charges are **not unit-detail
  rows**, for either the single-unit main table or multi-unit appendix. Its
  bottom totals sum only the visible rental rows and their real taxes; they do
  not silently include hidden charges. A note distinguishes unit totals from
  the full invoice total.
- First-page invoice totals still include all actual fees and taxes. DPP still
  excludes Biaya/stamp duty. The totals box discloses fee subtotals separately,
  including legacy/manual `Biaya Materai` lines without the stamp marker. PPN,
  PPh, paid amounts, Terbilang and Total remain the actual accounting values.
  Native rounding/other adjustments are not forced onto a vehicle's price/tax.
- This is print-only: no order, Billing Engine, invoice line, journal, payment,
  tax setup or historical amount is written. Existing stored PDF attachments may
  need the normal re-render workflow to display the new layout.

## Required Rental Order header

Rental quotations require Customer, Attention/UP, Quotation Date, Pricelist,
Payment Terms, Rental Type, Location, both Estimate Rental Period dates,
Invoicing Frequency, Weekend Rule Adjustment, TOP, Billing Calculation Method,
Grouping invoice and Invoice Print/Preparation Lead Time. These fields are
marked required in the draft/sent form. **Invoicing Day** is required only for
Grouping All Unit; Separate by Delivered Date continues using actual delivery
dates without requiring an invisible invoice-day field. **H-0 is valid**;
negative preparation lead time is rejected at confirmation.

Confirm Order checks the same inputs server-side, including API/import calls,
before confirmation, stock operations, Billing Engine creation or the Customer
PO price warning. The error lists every missing input per order. An invalid
quotation in a batch prevents partial confirmation. RPC can still create a
partial draft automatically, but the user must complete it before confirming.
Actual Rental Period and calculated Total Months/Duration/Return Status are
not required quotation inputs: actual dates still follow delivery/fallback
logic. Already-confirmed historical orders are not backfilled or blocked by
this new quotation check. Ordinary non-rental sales retain their existing
requirements. Billing formulas and the one-save/regeneration limit are unchanged.

## Customer defaults for Rental Orders

In **Contacts > Sales & Purchase > Default Rental Order**, configure TOP,
Weekend Rule Adjustment and Billing Calculation Method. The selected contact's
values take precedence; blank fields fall back individually to the commercial
parent company. If neither is configured, the order's normal defaults remain
(Keep Original Date for weekends; TOP/calculation method remain unset unless
another explicit default was supplied).

These are copied values, not related/computed links. Customer selection on a
new/quotation Rental Order loads them; the user can edit the order afterwards.
Saving/reopening does not reset manual choices. Changing customers in a
quotation reloads the new customer's defaults. Existing confirmed orders and
used billing-amendment allowances are not auto-updated. Existing edit rules
remain: Weekend Rule/Calculation Method lock after confirmation; TOP retains
the one-save amendment/one-regeneration workflow.

Server-side batch create/import and RPC-generated Rental Orders also receive
missing defaults. Explicit order values and explicit context defaults take
precedence, and duplicating an order preserves its copied billing choices.
Ordinary Sales Orders are unaffected. Updating customer defaults never changes
old quotations, Billing Engine schedules or invoices, and does not change any
billing formulas.

## Customer PO price at confirmation

Rental Orders show **Harga PO Customer** below **Tanggal PO Cust.** in Other
Info, in the order's currency. Drafts can still be saved without it, but
Confirm Order requires a positive value. It is compared to **Total**
(`amount_total`, including taxes), not the full-tenor Total Keseluruhan, using
the currency's rounding precision. Matching values confirm normally.

Different values open a warning with the PO/SO amounts and difference.
**Batal** leaves all selected quotations unchanged; **Tetap Konfirmasi**
continues normal confirmation, without changing either amount. The server
rechecks required values, permissions and the warning's order/amount snapshot;
changed values require a fresh warning. Batch confirmation waits for the
warning before confirming any selected order. Existing stock/Billing Engine
confirmation behaviour is retained.

Ordinary non-rental sales are unaffected. Existing confirmed Rental Orders
are not backfilled or revalidated merely by upgrading/saving. The field is
tracked and reset when duplicating an order. No pricing, taxes, Billing Engine
formulas or existing invoice amounts are changed.

## Return ET

Request ET now opens the separate **Return Picking ET** wizard/table. Its
initial zero-quantity rows are the current order's delivered units with both
Returned and Returned ET equal to zero. Only positive quantities selected by
the user are returned. Units on different completed deliveries can be selected
together; one native return picking is created per original delivery.

The native return factory handles original-move links, locations, confirmation,
reservation and validation. Non-cancelled returns already in progress consume
the available quantity. Submission is atomic and rechecks eligibility and
permissions under the order lock, preventing a repeated ET submission.
Ordinary Return popups exclude units already reserved by an ET return, and
recheck this when submitted, including popups opened before the ET request.

**Returned ET** is a stored computed Float, separate from ordinary Returned.
It increases when the marked return is **Done**, not merely when requested.
Ordinary Returned excludes these ET moves. Both count towards the order's
existing return summary and Return-button availability. Billing Engine shows
**Status Unit** with Return ET taking precedence over Returned, then Delivered;
undelivered units remain blank. Existing returns stay ordinary returns.

On Return ET submission, the existing Request Early Termination tab records
the selected units and generated pickings. Penalty Amount snapshots **25% of
the selected units' Billing Engine amounts** whose invoices are absent, Draft,
or posted Not Paid. Paid, Partially Paid, In Payment and Cancelled invoices are
excluded. A grouped invoice contributes only the selected sale lines, not the
whole invoice or unrelated units with the same product/blank/reused plate.
Amounts come directly from Billing Engine, including forecasts beyond the
six-month invoice batch; no taxes, stamp duty or invoice totals are added.

The existing single-request-per-order approval workflow remains: header
Approve ET is removed, while the director/delegation approval button inside
the tab is retained. Existing invoices are not changed, no penalty invoice is
created merely by Return ET, and rental-invoice scheduling is not modified.
Cancelling the popup does not submit an ET request. Historical returns are not
reclassified during upgrade.

Legacy pending/unapproved ET requests without an ET picking can enter the new
wizard. Merely opening it preserves their existing penalty and notes; a
confirmed Return ET explicitly recalculates the selected-unit penalty and
records the picking. Approved legacy ET requests cannot be reopened/repriced.

## Generate Invoices: six-month batches

The **Orders > Generate Invoices** wizard creates draft invoices for a maximum
six-month span of Billing Engine **period starts**, separately for each Rental
Order. It begins at the earliest eligible period without an invoice, after
linking any exactly matching legacy invoices. It does not use today's date,
Invoice Date, or Invoice Draft Date as the batch boundary.

For monthly billing, if January is already invoiced, the next run covers
February-July; another run covers August-January. If January and February are
already invoiced, the next run starts in March. Existing invoice links prevent
duplicate billing; a deleted draft or late-delivered unit is picked up from
the earliest outstanding period rather than silently skipped.

This limits the calendar span, not the number of invoices. Grouping, TOP,
weekend adjustment, preparation lead time, prices and tax formulas are
unchanged. Per 3 Months normally produces two invoices per billing group per
batch; Per 6 Months produces one. Yearly and As Duration rows are kept whole,
including their original dates and amounts, even if they cover over six
months. No frequency period is split or repriced.

At the contract end, only the remaining Billing Engine periods are invoiced.
Orders awaiting regeneration or with unmatched legacy invoices retain the
existing skip/report behavior. Cron still processes due preparation dates
without the six-month manual batch cap; legacy Trigger All also retains its
explicit all-period behavior. The underlying generator's batch limit is
optional for those existing callers. No existing invoices or engine schedules
are deleted or regenerated by this change, and no data migration is required.

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

Customer PDF dates use English `MMM d, yyyy` (for example `Oct 8, 2031`),
including rental ranges in generated/legacy numeric descriptions. In the
multi-unit main summary and ordinary non-rental invoices, identical printed
descriptions are grouped within each section/note block, summing
quantity and the original rounded line amounts. Unit identifiers are collected
separately, so different units can share a product/period row. Different periods
or description notes remain separate; different rates/discounts use weighted
printed values.
Single-unit rental detail tables and multi-unit appendices are not grouped.
No journal items or saved descriptions are merged or rewritten.

Rental invoices now show actual vehicle registrations (for example `B 1234
ABC`), never FN/asset codes, in the **No Polisi** detail column. The old inline
comma-separated/vertical **List Nopol** treatment remains only for ordinary
non-rental customer invoices; rental appendices replace it without duplication.
A saved real registration on the invoice line takes
precedence for historical accuracy. Otherwise registrations are resolved from
the invoice's analytic accounts, their uniquely linked fleet vehicles, or
linked sale lines/legacy registration paragraphs. Native composite multi-plan
keys and inactive accounts are supported; vehicle analytics are preferred over
department accounts. Missing or ambiguous registrations are not fabricated,
and an FN/name/reference is never used as a substitute for a registration.

The bordered totals show a print-only DPP excluding stamp duty and any product
line whose description contains the word `Biaya` (case-insensitive), including
legacy charges without the stamp-duty flag. PPN, PPh, Total and Terbilang still
use the unchanged accounting values. Fee lines are omitted from unit-detail
tables and disclosed separately in first-page totals. Payment instructions and
all stored terms stay in a bounded left column beside the totals.

The customer totals use a separate, border-box outer frame with a small right
inset and single internal cell borders, avoiding wkhtmltopdf clipping of the
right edge inside the native floated/overflow wrapper. Native company table
styling is opted out only on this customer totals table. Vendor bills retain
their native table styling. DPP, taxes, fees, total, payment rows and journal
items are unchanged; existing posted invoices can be reprinted without editing
their accounting entries. Optional Poppler-based tests inspect the rendered
PDF's left/right outline, not only its CSS declarations.

Terms and Conditions render the invoice's complete stored `narration` HTML,
including all legacy/custom clauses, without changing that field or posted
entries. Only when this field is empty (including visually empty HTML), the
report uses the four approved payment/confirmation/correction/PPH 23 clauses.
There is no two-clause or four-clause limit on existing invoice terms.

New Billing Engine descriptions store the real registration (not the FN asset
number), with rental dates in `dd-mm-yyyy`. For old rental invoices, a report
helper removes generated RPC references/plate labels and formats dates without
rewriting posted invoice lines. The PDF details resolve the real registrations
described above without changing the summary's quantities or amounts. The
generator's registration resolution remains unchanged and never invents a
registration from an FN asset identifier.

## Verification

Native Odoo tests cover actual accounting totals, withholding/PPN, idempotent
generation, preserving old invoices, and real one-page/multipage PDF rendering.
For 0.50, all **57 invoice/PDF tests passed** on a disposable database (32 report
regressions and 25 detail-table tests). Final patched-Qt PDFs were rendered and
visually checked: one-unit output is one page; 12-unit output has a grouped main
page followed by a fee-free unit appendix. Legacy missing rental flags,
understated Input Order quantities, five-clause terms, fee quantities and
unchanged posted accounting values are covered. No staging data was changed.
For 0.49, all **51 invoice/PDF tests passed** on a disposable database (32 report
regressions and 19 detail-table tests). Real patched-Qt PDFs were visually
checked for single-unit, 12-unit, 65-unit, long-description and batch output.
The full-module run executed 211 tests with 7 existing assertion failures in
`test_customer_po_price`: the tests expect `Harga PO Customer`, while the
unchanged application/wizard labels already say `Total PO Customer`. Those
unrelated source and test files were not modified by this report change.
Optional test-only PDF exports use `INVOICE_PDF_QA_DIR`.
For production-equivalent multipage pagination, use wkhtmltopdf with patched Qt;
the distribution's unpatched Qt build can split table rows despite print CSS.
