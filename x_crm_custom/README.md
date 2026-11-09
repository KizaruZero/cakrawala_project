# CRM company and contact (19.0.1.0.14)

## Harga Sewa/Bulan and Harga OTR as Monetary (19.0.1.0.14)

`sewa_per_bulan` and `harga_otr` now use Monetary fields and widgets with native
CRM `company_currency`, just like Total Forecast/Expected Revenue. They remain
editable in Offering, with the original required/readonly stage modifiers and
force-save behavior. Company currency and standard currency precision apply;
no exchange-rate conversion, new quantity multiplier or RPC mapping change is
introduced. Total Forecast still equals Harga Sewa/Bulan × Masa Sewa.

Upgrade `x_crm_custom` to **19.0.1.0.14** for the two Float-to-Monetary schema
conversions and reload the browser. No custom historical backfill or financial
transaction regeneration is performed. Earlier CRM changes are included.

Verification: 137 RPC/CRM regression tests pass, including form input, native
currency rounding, persisted prices, approved-RPC synchronization and the date
browser runner. A native upgrade from simulated pre-0.14 Float columns and
metadata preserves saved rent 4,300,000.50, OTR 451,100,000.25 and forecast
154,800,018.00 while converting both columns to numeric/Monetary. All checks
use an agent-owned disposable database, not operational or staging data.

## Total Forecast as Monetary

`total_forecast` is now a stored, computed Monetary field using CRM's native
`company_currency`, also used by Expected Revenue. The form uses the native
monetary widget and remains read-only. Currency follows the lead's company,
falling back to the active company for leads without a company (IDR displays
Rp). Currency precision/rounding follows Odoo's standard Monetary behavior.

The formula remains **Harga Sewa/Bulan × Masa Sewa**, without a quantity
multiplier. There is no exchange-rate conversion or change to other amounts.
Upgrade `x_crm_custom` to **19.0.1.0.13**; Odoo handles the stored Float-to-Monetary
column conversion. No data deletion, historical transaction regeneration or
custom backfill is required.

Verification: five new forecast tests pass (field/view definition, unchanged
formula without quantity multiplication, native company/fallback currency,
currency precision and stored values, and form onchange/read-only behavior).
The fresh-install RPC/CRM regression run passes 133 tests, including the date
browser runner. A native upgrade from a simulated pre-0.13 double-precision Float
column and metadata also preserves a saved 180,000,000 forecast and converts the
column to numeric/Monetary. All checks use an agent-owned disposable database.

## Estimated Delivery date display

Estimated Delivery in the CRM form now displays **01, Feb 2026** (two-digit day,
comma, English abbreviated month and four-digit year). The scoped
`crm_estimated_delivery_date` widget extends Odoo's DateTimeField, preserving its
native picker, editing, validation and ISO Date storage. Numeric tooltips/active
date input retain native behavior. Other CRM/Odoo date fields, language date
settings, date values and transfers to RPC/rental transactions are unchanged.
Empty dates remain empty. Upgrade `x_crm_custom` to **19.0.1.0.12** and reload the
browser to load the new field asset. No data migration is needed.

Verification: **43 CRM/Odoo tests pass**, including the native Chrome/HOOT
browser runner with **four frontend checks** (readonly format/other-date
isolation, calendar editing + ISO save, empty dates and immutable leap-year/
locale formatting). Existing RPC regressions also passed in the fresh-install
run. Browser tests need Odoo's optional `websocket-client` test dependency; QA
installed it only under the disposable test directory, not in the live venv.

## Hidden Merek in Offering

Merek is hidden in the CRM form, not deleted from the model or existing leads.
Users select a vehicle **Tipe** directly; its product template is copied to the
hidden Merek by the form onchange and by create/write when Tipe is supplied.
The Tipe domain now allows vehicle variants without requiring a template to be
selected first. The hidden field is no longer a separate required stage input;
the Tipe requirement remains. RPC creation still uses the variant/template as
before. Unrelated saves do not clear or rewrite existing Merek values.
Upgrade `x_crm_custom` to **19.0.1.0.11** to apply the view; no data migration is
needed and no existing leads or RPCs are bulk-rewritten.

Verification: **40 CRM tests pass**, including four new regressions for hidden
field/domain behavior, variant-to-template API/RPC mapping, form onchange/save,
and legacy/bulk updates. The 10 OTR Many2many tests from the preceding change
also pass with CRM installed (50 tests in total), using a disposable database.

## Company and contact

Deploy and upgrade `x_crm_custom`; no staging records are changed by the source
patch itself.

Quick Create now selects **Company** (`partner_id`) first, then **Contact**
(`contact_partner_id`) from that company's contact persons. The full form uses
the same separation for Existing Customer and Contact Name. Contact selection
copies the PIC's name, job position (`res.partner.function`), email and phone
onto the lead. The address and customer for newly created RPCs remain the
company. Opportunity-name uppercasing and stage requirements are retained.

CRM Company/Existing Customer and Contact/Contact Name widgets explicitly use
`show_vat=False`, so their dropdown and selected labels do not append NPWP,
even if the enclosing action/context requests tax IDs. The copied Contact Name
continues to use the contact's actual name, not its decorated display name.
This is a CRM presentation setting only: it does not copy, clear or modify VAT
on existing company/contact masters, alter native tax-ID inheritance, remove
NPWP from master forms or invoices, or disable fiscal validation.

The copied details remain editable snapshots. Unrelated saves or master-data
changes do not reset manually entered lead details. Changing company clears a
PIC from a different company, and selecting an unrelated PIC is rejected on
the server as well as filtered in the form. Lead email/phone edits while a PIC
is selected do not write PIC data onto the company's or contact's master data.

API/import calls that still send a company-owned contact as `partner_id` are
normalized to company + PIC. Standalone historical individuals are not assigned
an invented company. The New Customer/Offering flow creates a company and a
separate child contact when a contact name was supplied.

On upgrade, the versioned migration separates old leads whose customer is
still a contact person under a company, including archived leads/contacts. It
preserves manual details, fills missing job information, and does not rename
leads or change their stages. Conflicting explicit PIC links are left for
review, and no contact is guessed from a name. Existing RPCs, quotations,
orders and posted invoices are not re-linked or rewritten.
