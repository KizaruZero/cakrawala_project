# X Asset Leaseback — 19.0.1.0.7

## Vehicle Duration default

Selecting Vehicle on a new/Draft asset fills Duration (`method_number`) from
**Sisa Umur Depresiasi (Bulan)** (`leaseback_remaining_duration`) of the latest
real main asset for the same Vehicle and company, including archived
assets. Latest means `create_date DESC, id DESC`; acquisition dates and later
edits do not reorder history. Asset models and gross-increase child assets are
not sources. The current asset is excluded, and normal read permissions apply.

For example, an old asset with full Duration 96 and remaining duration 84 defaults
the new asset to **84**, not 96. The stored remaining value is copied exactly;
zero/unfilled does **not** fall back to the original duration or an older asset.
The user can enter a valid Duration manually before computing depreciation if
the remaining field has not been populated. No depreciation method, period
unit, acquisition date, values or posted entries are copied or
changed. Duration remains manually editable. Explicit Duration in create/write
values (or a create context default) takes precedence. Native model selection
on a fleet form still applies its other defaults, then restores the matching
vehicle's remaining duration. Without a matching asset, native defaults remain unchanged.

For an existing unposted Draft created under the earlier full-Duration rule,
clear and reselect Vehicle to reload the remaining-month default, or edit
Duration manually. Existing records are not silently backfilled on upgrade.

Running/closed assets and Drafts with posted depreciation entries are not
automatically updated. Changing Duration on an unposted Draft invalidates its
old Draft board, as with a native manual Duration edit; recompute/Confirm builds
the new board. Historical source assets are never modified by this default,
and upgrade does not backfill Duration or recompute existing depreciation.

## Existing blockers are unchanged

- `account.asset.vehicle_id` is Many2one: one asset selects one Vehicle. Native
  source journal lines cannot contain more than one distinct Vehicle.
- The custom `_check_single_asset_per_vehicle` guard runs on create and writes
  of Vehicle, Active or Parent. It rejects a second **active main asset** linked
  to the same Vehicle. Draft and closed/custom Leaseback/Sell/Dispose states are
  still included when active; models, children and archived assets are excluded.
  This is not a new Confirm-only check. The default does not bypass it.
- Confirm requires Asset Model, and fleet assets require Vehicle and its
  Analytic Account/distribution. Native accounting/depreciation checks remain.
- Native archiving requires state `close` or `model`. The existing custom
  Leaseback/Sell/Dispose states do not automatically satisfy that native check;
  this patch does not change archive policy or automatically archive anything.

Deploy and upgrade **x_account_asset_leaseback 19.0.1.0.7**. Staging is not
changed by this local patch. No permission/duplicate/depreciation-policy change
is included.

19.0.1.0.7 QA (2026-11-13): **27 targeted native Odoo tests passed (0 failures/
errors)**: 21 Duration/default/guard cases and 6 existing refinancing regressions.
All history fixtures deliberately use different full and remaining durations.
Includes the 96-full/84-remaining case in create and native Form, latest zero or
unfilled remaining values without fallback, manual overrides and unchanged
posted history/Vehicle uniqueness rules. The disposable QA DB was removed;
log retained at `/tmp/cakrawala-asset-remaining.zf1QOJa5/tests.log`.

Previous 19.0.1.0.6 QA (2026-11-13): **25 targeted native Odoo tests passed (0 failures/errors)**:
19 new Duration/default/guard cases and 6 existing refinancing regressions.
Includes native Form selection/manual overrides, creation ordering, archives,
source/model/child/company exclusions, API create/write/context defaults,
unposted-board invalidation, posted-history preservation, and the unchanged
duplicate/archive/Confirm rules. The isolated no-demo QA environment includes
`hr_fleet` because an existing stock/Fleet view references `mobility_card`.
The disposable QA database was removed; logs retained at
`/tmp/cakrawala-asset-duration.8mCUCjWq/tests3.log`.
