# Rental Profit Calculation

## Authorized internal Funding Hierarchy synchronization (19.0.1.0.118)

After validating **RPC: Finance** (also inherited by RPC Manager) and the user's
write access/record rules on the RPC, internal generation may synchronize the
three Funding Hierarchy master models with elevated access. The scope is only
these fixed master models: hierarchy names/sequences are derived from the
Manager-controlled Hierarchy Logic and the existing fixed summary labels. RPC
state changes, financial line generation and approval still run as the caller.
No public action or client context flag exposes the synchronization helper.

Manual master create/edit/delete remains **Manager only**: no ACLs, memberships,
formulas or historical transactions are changed. This permits a Finance-only
user to submit/confirm Finance without granting them general master maintenance
rights. Upgrade `x_rental_profit_calculation` to **19.0.1.0.118** to apply this
and the preceding button/OTR fixes.

Verification: **125 tests pass** (85 RPC + 40 CRM). Coverage includes Finance-only
Submit Finance and Confirm, denied manual create/write/unlink on all three master
models, Manager manual access, unchanged user memberships, denied internal sync
for non-Finance roles, RPC record-rule enforcement before elevation, and reuse/
reactivation of existing masters without duplicate creation. Financial/report
regressions also pass. The test database is agent-owned and disposable; no
operational or staging records are modified.

## Workflow button role audit (19.0.1.0.117)

| Buttons | Required RPC Role |
| --- | --- |
| Submit (Draft), Create Quotation (form and multi-select list) | Marketing |
| Submit Purchasing | Procurement |
| Submit Operation | Operation |
| Submit Finance, Confirm, legacy Finance Submit alias | Finance |
| Approve, Revise, Reset ke Draft; revision/final-price wizard actions | Manager |

Manager retains the department actions through the existing implied groups.
Approval still also requires the assigned approver or a valid delegation for the
current stage. Existing stage and business validations remain; Reset ke Draft
now checks Cancelled on the server as well as in the form. Quotation creation,
opening/confirming a revision and resetting have server-side role checks, not
just button visibility. The Cancel legacy alias shares the revision guard.
Read-only Print RPC and smart-button navigation continue to use existing record
access rights. No roles are assigned to operational users and no historical
documents or formulas are migrated. Upgrade to **19.0.1.0.117**, which includes
the preceding fixes and OTR migration.

The initial audit exposed a Finance-only ACL conflict (119/120 tests): automatic
Funding Hierarchy synchronization attempted Manager-only master writes. The
user authorized the narrowly scoped internal synchronization implemented in
19.0.1.0.118 above, retaining the manual master ACLs.

## Submit Purchasing role (19.0.1.0.116)

The Submit Purchasing button and its server action require **RPC: Procurement**,
not RPC: Marketing. The button still applies only in Submitted; the action still
requires positive Harga OTR and moves the document to Procurement Done. RPC
Manager retains access via its existing implied Procurement group. No role
assignments, financial formulas or historical transactions are migrated.
Deploy and upgrade `x_rental_profit_calculation` to **19.0.1.0.116**; upgrades
from older versions still execute the 19.0.1.0.115 OTR Many2many migration below.

Verification: **72 RPC tests pass**, including six new access regressions using
non-superuser Procurement, Marketing, Operation, Finance and ordinary internal
users, the RPC Roles selector and Manager's implied Procurement role. Existing
workflow/price guards and the other RPC tests pass unchanged.

## OTR categories: multiple vehicle types (19.0.1.0.115)

**Kategori Kendaraan OTR → Jenis Kendaraan** now uses required Many2many
tags (`jenis_kendaraan_ids`) in both the editable list and the form. Only
`rpc.parameter` records of type `jenis_kendaraan` are accepted. The vehicle type
on the RPC document itself remains a single selection.

Automatic insurance category matching uses membership in those tags and the
existing OTR Leasing range: `otr_from <= otr_leasing <= otr_to`; `otr_to = 0`
means no upper limit. Archived categories are excluded. Existing inclusive
boundaries and the `otr_from, id` first-match priority are unchanged. If master
ranges overlap for the same vehicle type, only that first category supplies the
rate; rates are never summed across types/categories. Avoid overlapping ranges
when distinct rates are intended.

Insurance still selects one rate by **Wilayah + Kategori OTR + Asuransi Type**.
Annual amount remains **rate × OTR Final**, and the annual row count remains
`ceil(Masa Sewa / 12)`. Other purchasing, financing, service, STNK, profitability
and report formulas are unchanged. A document's manual category override still
lasts until its vehicle type or OTR Leasing changes. Editing category master data
does not automatically rebuild historical insurance/financial schedules.

Deploy the code and **upgrade `x_rental_profit_calculation`**. The post-upgrade
migration fills empty Many2many mappings from the old scalar ID (or legacy code),
including archived/custom categories and inactive types. Already populated
Many2many mappings are never overwritten; rerunning the migration is safe.
Existing document categories, approval states, insurance rows and monetary
results are not recomputed by the migration. Original single-valued columns are
retained for compatibility with previous migrations/imports. They represent a
type only when exactly one tag is selected; all new matching uses the Many2many.

Tests: `--test-tags=/x_rental_profit_calculation:TestRpcOtrVehicleTypes` covers
multi-type matching, OTR boundaries/changes, archive handling, first-match
priority, unchanged insurance formulas/manual overrides, validation, legacy
inputs, copy/form behavior, original seed mappings and idempotent migration.

Verification: all **66 RPC tests pass**, including 10 new vehicle-type tests.
A native module upgrade from a simulated scalar-only schema also restores all
eight original mappings. Tests and upgrade verification use an agent-owned
disposable database, not the operational/local staging database.
