# Leasing Amortization Schedule - 19.0.1.0.7

## Bunga Efektif 2

- A separate `Compute Method = Bunga Efektif 2` (`effective_2`) is available on
  Leasing Schedules and the compute wizard. It reuses the main Amortization
  Schedule table. The existing Bunga Efektif and Bunga Flat calculations remain
  unchanged. A Draft-only **Compute Efektif 2** button also allows recalculation
  after unlinked schedule rows already exist.
- Initial principal is exactly **Total Hutang**, not an automatic replacement
  with Harga OTR minus DP. The annual Interest field is a percent (12 means 12%).
  Monthly rate = annual Interest / 1200. A positive **Cicilan Per Bulan** is used,
  otherwise the existing stored PO installment is used. If neither is filled,
  Compute asks for the contractual installment; there is no automatic PMT or
  silent estimated installment for this method.
- First-row interest = Total Hutang × monthly rate; first-row principal =
  installment − first interest; remaining principal = Total Hutang − first
  principal. From row 2 onward, interest is previous remaining principal ×
  monthly rate, and principal = installment − interest. Interest is rounded
  half-up to currency precision. Dates follow the shared header due-date rule,
  not elapsed calendar-day interest. ADDM/arrears do not suppress first interest.
- The final installment pays the entire remaining principal plus that month's
  interest, as in the existing Effective flow. Its amount may differ from the
  contractual regular installment. Invalid/negative inputs, an installment below
  monthly interest or one that repays principal before the stated final period
  are rejected without replacing existing rows. For a one-period contract the
  supplied installment must equal principal plus first-month interest.
- Header Total Pembayaran Cicilan and Total Bunga include **all** rows, including
  the first. Header Saldo Pokok Hutang represents initial Total Hutang; each
  row's Saldo Pokok shows the remaining principal. First Saldo Bunga = header
  Total Bunga − first interest; the final principal and interest balances are 0.
  Example: Total Hutang Rp100,000,000, annual Interest 12%, installment Rp3,000,000:
  row 1 interest Rp1,000,000/principal Rp2,000,000/balance Rp98,000,000; row 2
  interest Rp980,000/principal Rp2,020,000/balance Rp95,980,000.
- The same canonical `account.loan.line` rows feed payment journals, accrual
  journals (including first-row interest), Payment Date and principal-only Early
  Settlement. A calculation signature and independent formula checks protect
  stale/altered schedules; approved Draft-only manual due-date edits preserve
  amounts and refresh that signature. Recalculation/reset/parameter or financial
  row edits are blocked once Running or linked to financial history.
- Switching methods requires Compute before Confirm. Preview is read-only until
  Apply, uses actual tenor months, and uses the same calculator as the final
  schedule. Existing schedules are not switched or regenerated during upgrade.
  The standalone `leasing.simulation` model remains outside this change.

## Due dates, editable Draft dates and schedule numbering

- **Tanggal Mulai Leasing** replaces the Leasing Start Date label. Tanggal
  Pencairan is hidden, not deleted. Neither field determines installment dates.
- Both Effective and Flat Compute require **Tanggal Jatuh Tempo** in the header.
  It is the first row's Due Date, for ADDM and arrears alike. Later rows use
  `first due date + N calendar months`, always anchored to that original date.
  Missing days use month end: Jan 31 -> Feb 28/29 -> Mar 31. Legacy end-of-month,
  first-payment override and Flat timing controls no longer override this rule;
  obsolete controls are hidden, but their stored historical data is retained.
- In both embedded tables, only **Due Date** can be edited while Draft. Payment
  Date and amounts are readonly; adding/deleting installments is disabled.
  Dates must remain chronological and unique so installment numbers and the
  principal/interest order cannot change. Any financial history blocks date
  edits, even if the document is Draft. Running dates are protected server-side.
- An approved manual Flat date edit keeps amounts unchanged and refreshes its
  calculation signature only after validating the original financial schedule.
  It does not waive stale parameters or altered principal/interest checks.
  Changing the header due date requires Compute again before Confirm. Compute
  explicitly replaces prior unlinked Draft rows, including manual dates.
- **Payment Date**, immediately after Due Date, comes from the Accounting Date
  of the actual Posted payment journal, using the existing custom or native
  payment entry link. It is empty before posting and after resetting to Draft,
  and follows a changed Accounting Date on repost. Accrued-interest and
  reclassification entries never populate Payment Date.
  The versioned upgrade migration recomputes this derived field in batches for
  existing/archived rows, without modifying journal dates, names, amounts or
  the installment Due Dates.
- New schedules always receive the Odoo `account.loan.leasing` sequence,
  `TA/CRS/MM/YYYY/00001`, including PO-generated schedules and copies. Month/year
  use the creation day in the user's timezone, not the first installment date.
  Name is readonly in the UI and cannot be renamed through write/API. Existing
  historical names are not renumbered during upgrade.
- No existing schedule is redated automatically. The new calendar policy is
  marked only on Compute. Historical Running Flat schedules preserve their old
  signature/calendar and remain payable. Recompute an unlinked Draft document
  explicitly to apply its header due date. Preview and Apply share this calendar
  and do not overwrite Tanggal Mulai Leasing with the first due date.

## Schedule footer totals

Saldo Pokok and Saldo Bunga are running balances and are not summed in the
installment-table footer (Effective and Flat). The footer still totals Pokok,
Bunga and Total Cicilan. This is a view-only change: row amounts, header totals,
formulas, payments and journals are unchanged.

## Bunga Flat - pokok dan bunga konstan

- `Compute Method = Bunga Efektif` retains its existing principal/interest
  calculation and summary semantics. Only its due-date/calendar policy and
  Draft-date editing follow the rules above.
- `Compute Method = Bunga Flat` displays **Amortization Schedule - Bunga Flat**
  immediately after the native schedule tab, and hides the native tab. The two
  tables are mutually exclusive. Flat is a separate UI table backed by
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
- This release replaces the previous equivalent-rate allocation for **new or
  explicitly recomputed Draft Flat schedules**. It no longer solves RATE or uses
  a declining-balance allocation. Let P be initial principal, C the contractual
  monthly installment and N the tenor: total contract interest B = C × N − P.
- For both ADDM and arrears, the first row displays **Pokok = 0, Bunga = 0,
  Total = C, Saldo Pokok = P − C, Saldo Bunga = B**. Canonical accounting
  `account.loan.line.principal` remains C on that row: the UI uses the readonly
  `flat_display_principal` field to display 0. This distinction is intentional:
  the first actual payment must debit principal, reduce Outstanding Balance,
  and be excluded from the remaining Early Settlement amount after payment.
  No additional accounting installment or journal is generated for this display.
- Rows 2 through N allocate **B / (N − 1)** interest and **(P − C) / (N − 1)**
  principal per month. The regular interest is rounded according to the header;
  regular principal is C less that rounded interest, so Total remains C. Both
  rounding residuals are placed in the last row, ending both balances at 0.
  A single-installment Flat schedule pays P with zero interest.
- ADDM and arrears both start on the explicit first due date. Their first row
  has zero interest under the requested Flat rule. Scheduled due dates do not
  populate Payment Date; only actual Posted payment entries do so.
- Dates follow the header due-date anniversary (no February drift).
  IDR interest follows the header's whole-rupiah half-up rounding or
  currency-precision choice. Currency precision is always used for non-IDR.
  The final residual keeps total contract interest and principal exact.
  For a zero-interest schedule, rounding is instead adjusted in the final
  principal-only payment. Invalid/underfunded contracts are rejected.
- Flat header totals include all installments, including the first ADDM payment:
  initial Saldo Pokok Hutang = principal; Total Pembayaran Cicilan = sum of all
  payments; Total Bunga = sum of all interest. Outstanding Balance continues to
  follow actual posted payments through the existing flow.
- Example: P = Rp787,500,000, N = 36, C = Rp25,353,000, B = Rp125,208,000.
  After row 1, principal is Rp762,147,000 and interest remains Rp125,208,000.
  With Rupiah Penuh, rows 2–35 have principal Rp21,775,629 and interest
  Rp3,577,371. Row 36 has principal Rp21,775,614 and interest Rp3,577,386.
  With currency precision 0.01, regular amounts are Rp21,775,628.57 and
  Rp3,577,371.43; last amounts are Rp21,775,628.62 and Rp3,577,371.38.
  Every payment remains Rp25,353,000; both final balances are 0. The old
  Efektif Ekuivalen field is not shown for the new constant-allocation schedule.

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
  New schedules are marked `constant_v2`; the new version field has no default,
  so old rows are not relabelled. Draft schedules from the previous formula
  require an explicit Compute before Confirm. Legacy Running Flat schedules
  display a warning and retain their previous amounts, display and transaction
  flow. Existing signatures continue to detect changed legacy rows/parameters,
  without comparing those historical rows against the new formula. Accounting
  must review the contract before migration; linked history is never replaced.
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
For 0.7, **115 tests passed (0 failures, 0 errors)** on a disposable database.
The 28 additional Effective 2 tests cover the first/subsequent declining-balance
formulas, full-tenor currency rounding and zero ending balances, mandatory
contractual installments (header or stored PO value), Total Hutang as principal,
header/row interest balances including the first month, preview/Apply and native
wizard Form switching, Draft-only date edits, stale/history guards, access
rights, actual payment/accrual posting and principal-only early settlement.
The previous 87 Effective/Flat/date/settlement regressions also remain passing.
For 0.6, **87 tests passed (0 failures, 0 errors)** on a disposable database.
This includes native Form edits in both tables (date editable, amounts readonly),
due-date calendar anchors/leap years, stale-header and financial-history guards,
automatic numbering/copy/read-only enforcement, posted journal accounting-date
changes and resets, and the upgrade-only derived Payment Date refresh. All
previous calculation, payment and early-settlement regressions remain covered.
For the 0.4 calculation baseline, **69 tests passed (0 failures, 0 errors)** on
a disposable local database. The 0.5 footer-only change was checked using Odoo's
native XML inheritance routine for the Effective list and the Flat table;
balance sums are absent while principal/interest/payment sums remain. The
existing native-view tests also contain these assertions for future suite runs.
The suite covers all 36 constant-allocation rows, ADDM/arrears, contractual
and automatic payments, rounding, zero interest, foreign currency, dates, native
form inheritance, stale/history protection, wizard preview/Apply, real payment,
first-row zero display versus real principal payment, legacy upgrade safety,
accrual and early-settlement integration, native access rights, and direct
Effective-versus-original calculation/preview regression checks. It also retains
all 32 original Pelunasan Dipercepat tests, including native bill posting,
source preservation, tax exclusion, company isolation and duplicate prevention.
No staging transactions were created or changed.

Deploy the source and upgrade **x_leasing_amortization** to **19.0.1.0.7**.
For an existing unlinked Draft Flat schedule (such as the staging test record),
click **Compute Flat Schedule** again to explicitly replace the previous formula.
Do not change a Running Effective schedule to Flat to test this feature; create
a separate Draft test schedule instead. No historical schedule or Vendor Bill
is generated automatically during upgrade.
