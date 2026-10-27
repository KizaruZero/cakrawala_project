# Leasing Amortization Schedule - 19.0.1.0.3

## Bunga Flat - alokasi efektif ekuivalen

- `Compute Method = Bunga Efektif` retains its existing calculation, preview,
  table, dates and summary semantics. The new Flat implementation delegates
  Effective calculations to the original methods; it does not replace them.
- `Compute Method = Bunga Flat` displays **Amortization Schedule - Bunga Flat**
  immediately after the native schedule tab, and hides the native tab. The two
  tables are mutually exclusive. Flat is a separate readonly UI table backed by
  the **same `account.loan.line` installments**, not a second accounting schedule.
  Ordinary payments, accrued-interest journals and Pelunasan Dipercepat therefore
  retain the original source links and transaction flow.
- On a Draft loan, select Advarr, enter the annual Flat rate and tenor in months,
  then use **Compute Flat Schedule**. Principal is Harga OTR less Down Payment;
  if OTR is absent, Total Hutang is used. Down Payment must be nonnegative and
  smaller than OTR. No extra period is added to the tenor.
- A positive **Cicilan Per Bulan** from the contract takes priority. If empty,
  the existing PO installment is used when present. If neither is supplied:
  `monthly installment = principal / months + principal × annual Flat % / 1200`.
  The result uses currency precision, with no automatic rounding to thousands.
  An automatically computed amount remains automatic when parameters change;
  explicitly entering an installment locks it as a contractual amount. The
  readonly **Sumber Cicilan Flat** indicates Automatic versus Contract.
- The quoted Flat rate determines automatic pricing, **not a constant interest
  amount per row**. Allocation solves the monthly equivalent annuity rate from
  principal, installment, tenor and payment timing (Excel RATE type 1 for ADDM,
  type 0 for arrears). The displayed annual equivalent is that monthly rate × 12,
  not an annual compounded yield. The actual implied Flat rate is also displayed,
  since a contractual installment can differ from the quoted-rate calculation.
- ADDM has exactly `months` installments, the first on Leasing Start Date with
  zero interest. Subsequent interest is remaining principal × equivalent monthly
  rate. Arrears starts one month after Leasing Start Date and includes interest
  in the first installment. Scheduled due dates do not populate Tanggal Bayar;
  only actual payment transactions do so.
- Dates default to the original start-day anniversary each month (no February
  drift). **Akhir Bulan** is optional; the first ADDM payment remains on the start
  date. IDR interest defaults to whole-rupiah half-up rounding as in the reference
  PDF. Currency precision is optional and always used for non-IDR currencies.
  The final interest residual keeps total contract interest and principal exact.
  For a zero-interest schedule, rounding is instead adjusted in the final
  principal-only payment. Invalid/underfunded contracts are rejected.
- Flat header totals include all installments, including the first ADDM payment:
  initial Saldo Pokok Hutang = principal; Total Pembayaran Cicilan = sum of all
  payments; Total Bunga = sum of all interest. Outstanding Balance continues to
  follow actual posted payments through the existing flow.
- PDF reference: principal Rp787,500,000, 36 ADDM installments of Rp25,353,000,
  quoted Flat 5.30%, equivalent annual rate 10.4404882280%, total interest
  Rp125,208,000. All 36 principal/interest/remaining-balance rows and anniversary
  dates match the supplied reference, including zero ending balances.

### Recompute and historical-data safety

- Flat recomputation replaces only an unlinked Draft schedule. Parameters and
  financial rows cannot be changed/recomputed once Running or linked to financial
  history (including cancelled history). There is no automatic history rewrite.
- A parameter/row fingerprint and an independent amount/date check require
  recomputing stale Flat schedules before Confirm or financial transactions.
  Switching a computed Flat schedule back to Effective also requires Compute.
- Flat preview is read-only until Apply. It uses months rather than rounding the
  tenor to whole years, and shares the same calculator as the final schedule.
- Existing schedules are **not automatically regenerated** during upgrade.
  Legacy Running Flat schedules without a new calculation signature display a
  warning and retain their existing transaction flow. Accounting must review the
  contract before any migration; this patch does not convert existing schedules.
- The standalone `leasing.simulation` model is outside this account.loan change
  and is unchanged. The existing `x_fleet_document` dependency declares the
  provider of the vehicle analytic field used by this module.

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

## Verification / deployment

Run the native isolated Odoo tests with `--test-tags /x_leasing_amortization`.
**65 tests passed (0 failures, 0 errors)** on a disposable local database.
The suite covers the reference PDF's complete 36 rows, ADDM/arrears, contractual
and automatic payments, rounding, zero interest, foreign currency, dates, native
form inheritance, stale/history protection, wizard preview/Apply, real payment,
accrual and early-settlement integration, native access rights, and direct
Effective-versus-original calculation/preview regression checks. It also retains
all 32 original Pelunasan Dipercepat tests, including native bill posting,
source preservation, tax exclusion, company isolation and duplicate prevention.
No staging transactions were created or changed.

Deploy the source and upgrade **x_leasing_amortization** to **19.0.1.0.3**.
Do not change a Running Effective schedule to Flat to test this feature; create
a separate Draft test schedule instead. No historical schedule or Vendor Bill
is generated automatically during upgrade.
