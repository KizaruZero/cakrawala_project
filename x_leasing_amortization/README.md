# Leasing Amortization Schedule - 19.0.1.0.2

## Pelunasan Dipercepat

- On a Running leasing schedule, the header button creates one **draft Vendor
  Bill**, with one item per remaining installment. Accounting/Invoicing access,
  company access and native bill permissions are required; no `sudo` is used.
- The boundary is the **last installment with a Posted payment entry** (existing
  `vendor_bill_id`, or a native generated principal-payment journal). The boundary
  is not the number of posted entries, payment date, current date, or a posted
  accrued-interest/reclassification journal. Earlier gaps are not included.
- Example: last posted installment 13 of 48 means installments **14-48 inclusive:
  35 bill items**, not 34. Each description is `Angsuran ke 14 - agreement_no -
  plate_number`; if Agreement No. is empty, the leasing document name is used.
- Quantity is 1, Unit Price is the source line's **principal** (including cents),
  Account is **Hutang Pokok (Long Term)**, and analytic distribution follows the
  loan's vehicle analytic account. There are no products, taxes, discounts,
  interest, fees or penalties. Theoretical remaining-balance columns are not used.
- The bill uses the leasing vendor/company/currency, today's invoice date, a
  Purchase journal for that company/currency, and the vendor's payment terms.
  Native vendor Payable is the counter-account. A Long Term account configured as
  Receivable/Payable or Off-Balance cannot be an invoice item in standard Odoo;
  a readable configuration error is shown without changing the CoA.
- Repeated clicks open the same active draft/posted bill. A cancelled/deleted
  draft allows regeneration. Existing installment payment links and all schedule
  amounts/dates are preserved; no existing journal is cancelled or replaced.
  An existing active payment journal within the remaining tail must be reviewed
  and cancelled separately before creating the bill.
- Bill and individual invoice items retain explicit source links. A separate
  smart button opens the bills, including cancelled history. Copies do not carry
  the source links. Creation/posting and the regular leasing payment wizard lock
  the loan to prevent concurrent duplicates. Regular installment payment is
  blocked for installments already covered by a non-cancelled settlement bill.
- Posting checks that the bill still matches the remaining original principal:
  newly posted payments, edited principal, extra items, tax, discount or quantity
  changes require correcting/cancelling the draft first.
- **No automatic posting, payment, closing, interest waiver, or accounting
  reconciliation is performed.** Posting this bill also does not set regular
  installments' payment dates/statuses or change the loan header balance.
  The existing interest accrual cron remains unchanged while the loan is Running;
  Accounting must review accrued interest and close the loan through the existing
  process when appropriate.

## Calculation change on hold

The requested PDF B2700KZI ADDM/equivalent-rate calculation remains **on hold**.
This change does not modify the effective/flat formulas, first-installment rules,
summary totals or existing amortization schedules. The `x_fleet_document`
dependency explicitly declares the existing provider of the vehicle analytic
field already used by this module; it prevents registry failure on a fresh install.

## Verification / deployment

Run the native isolated Odoo tests with
`--test-tags /x_leasing_amortization:TestLeasingEarlySettlement`.
All 32 tests passed on a disposable database, including the real inherited form,
native bill posting, principal-only amounts, source preservation, tax exclusion,
authorization/company isolation, duplicate prevention and ordinary bill/payment
regressions. No staging transactions were created or changed.
Deploy the source and upgrade **x_leasing_amortization** to **19.0.1.0.2**.
No historical bill is created automatically during upgrade.
