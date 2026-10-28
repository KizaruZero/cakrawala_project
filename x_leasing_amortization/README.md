# Leasing Amortization Schedule - 19.0.1.0.11

## Optional legacy identifiers on import

Agreement No., Leasing Contract No. and Plate Number may be blank or repeated
across contracts with different Import Keys. These identifiers no longer block
Draft imports. Plate Number links a Vehicle only when exactly one readable
vehicle matches within the selected company; otherwise the original text is
retained as **Plate Number from Import** and shown as Plate Number while no
Vehicle is linked. No Fleet record is created or overwritten and no arbitrary
match is selected. Imported Drafts allow selecting the Vehicle in the form.
Confirmation still requires Vehicle and Analytic Account under the existing
leasing rules. Financial reconciliation, company/access checks and unique
Import Key protection remain; formulas and existing transaction amounts are
unchanged. Use a consistent Import Key to avoid uploading the same contract twice.

## Calculation-method display name

`Bunga Efektif 2` is now displayed as **Bunga Efektif (Tanpa DP)** on schedules,
the compute wizard/button, previews and validation messages. The stored key
remains `effective_2`: no existing method, DP, installment, amount, signature,
date or transaction is migrated/recomputed. This is only a label change.
The upload template uses the new name; the importer still accepts the old
`Bunga Efektif 2` text as a compatibility alias to exactly the same stored key.

## PO-generated per-unit variant description

**Create Leasing Schedule** keeps creating one document per ordered vehicle unit
from the PO's Products/Order Lines, with the source `purchase_line_id` retained.
Each newly created schedule snapshots that line's Description (`name`) into
**Varian** (`vehicle_variant`), including a line-specific variant/description
even when several PO lines use the same product. If Description is empty, the
product display name is used. Receipt/Vehicle is not required to fill Varian.
The snapshot remains independent of later PO description changes and remains
editable while Draft under the existing form rules. Existing documents are not
overwritten/backfilled and the existing quantity/receipt mapping and financial
calculations are unchanged.

## Upload header and contractual schedules

- Open **Purchase > Import Leasing Schedules**, download the XLSX template,
  choose an active company, fill the `Header` and `Angsuran` sheets, and Import.
  The template includes Indonesian instructions and dropdowns for all three
  methods: Bunga Efektif, Bunga Efektif (Tanpa DP) and Bunga Flat. Keep column headers in
  row 1. Use plain numeric values and Excel dates or `YYYY-MM-DD`. Paste formulas
  as values before upload. The blank template contains no sample contracts to
  import accidentally.
- One Header row creates one standalone Draft loan with the complete schedule,
  without linking to or changing a Purchase Order. The name uses the existing
  readonly Odoo running number. Existing vendor, CoA codes and General journal
  code are resolved within the selected company; missing/ambiguous required
  references are rejected, not created or guessed. Vehicle matching is optional
  as described above; Analytic Account follows the linked Vehicle. Account
  settings must be complete before import. Only Accounting/Invoicing users with
  native model/company access can import; the importer does not use sudo.
- `Import Key` is a user-defined text key (maximum 80 characters), unique per
  company. Use that same key on every installment row. Uploading an existing key,
  including an archived contract, is rejected without replacing data. Agreement
  and contract numbers or plates may repeat on different Import Keys. Key checks are
  serialized and a database uniqueness constraint protects concurrent keys.
- Source is **Import Kontrak**, not Compute. Principal and interest follow the
  file, even when they differ from the formula for the selected method. There is
  no PMT/flat/declining-balance recalculation on upload or Confirm. The complete
  tenor is required: consecutive installment numbers 1..N, strictly increasing
  due dates, first date equal to First Due Date, nonnegative amounts at currency
  precision, principal total equal to Total Hutang, interest total equal to Total
  Bunga, and zero ending principal/interest balances. Optional Total and balance
  columns are independently checked when supplied. Negative or inconsistent
  rows are not rounded, repaired or silently ignored.
- Special Flat first row: `Principal = 0`, `Interest = 0`, and `Total = Monthly
  Installment` preserves the requested zero display while that payment reduces
  real principal. Its canonical `account.loan.line.principal` equals Total, so
  payment journals and early settlement do not lose that principal. Alternatively
  supply actual principal explicitly; its display then follows the file.
- Imported header totals include all installments, including the first. The
  existing canonical loan lines feed payments, accrued interest and early
  settlement. No second disconnected schedule table is created. Signature and
  reconciliation checks run before confirmation/payment/accrual/settlement.
  Financial rows and source metadata cannot be edited directly. Only due dates
  may be edited while Draft without financial history; they must retain order.
  Moving the first date also updates the imported header due date. Amounts are
  preserved. Compute, Reset, copy and switching back to Draft cannot overwrite
  imported schedules. Existing Compute-generated schedules are unchanged.
- No payment history, posted journals, historical paid statuses or Payment Dates
  are imported. **For an old contract, review Accounting's existing `Skip until`
  setting before Confirm**: the normal cron can accrue past-due interest once a
  contract is Running. The upload itself creates only Draft loans, no journals,
  payments or automatic confirmations. Historical payment migration/reconciliation
  is outside this feature.
- Maximum 5 MB, 100 contracts and 12,000 rows per sheet; macros and formulas in
  data sheets are rejected. All contracts are validated before creation and the
  upload is atomic: an error rolls back all contracts in that upload.

The distributed workbook is
`static/templates/Template_Import_Leasing.xlsx`. Its Header and Angsuran columns
are covered by a native regression test against the importer schema.

## Bunga Efektif (Tanpa DP)

- A separate `Compute Method = Bunga Efektif (Tanpa DP)` (`effective_2`) is available on
  Leasing Schedules and the compute wizard. It reuses the main Amortization
  Schedule table. The existing Bunga Efektif and Bunga Flat calculations remain
  unchanged. A Draft-only **Compute Efektif (Tanpa DP)** button also allows recalculation
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
For 0.10, **145 tests passed (0 failures, 0 errors)** on a disposable local
database. Selection/button/preview labels and the updated template are checked;
the legacy import label remains supported without changing contractual amounts.
For 0.9, **144 tests passed (0 failures, 0 errors)** on a disposable local
database. The six additional PO tests cover per-unit document counts, two
same-product lines with distinct descriptions, no-receipt creation, repeat-click
protection, adding only remaining quantities, manual/snapshot preservation and
the empty-description fallback. The previous 138 leasing regressions remain
passing; allocation formulas and transaction amounts are unchanged.
For 0.8, **138 tests passed (0 failures, 0 errors)** on a disposable local
database, including the previous 115 regressions. The 23 additional tests cover
contractual XLSX imports, reference/company/permission
checks, native Draft Form edits, atomicity, duplicate protection, and actual
payment/accrual/early-settlement posting from imported Effective/Effective 2/Flat
rows. Template validation lists, blank input sheets, headers and frozen panes
are verified against the exported XLSX.
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

Deploy the source and upgrade **x_leasing_amortization** to **19.0.1.0.11**.
For an existing unlinked Draft Flat schedule (such as the staging test record),
click **Compute Flat Schedule** again to explicitly replace the previous formula.
Do not change a Running Effective schedule to Flat to test this feature; create
a separate Draft test schedule instead. No historical schedule or Vendor Bill
is generated automatically during upgrade.
