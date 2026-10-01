# Validation — v1.3.1

Date: 2026-10-01

## Completed offline

- Manifest: version, dependencies, installable flag and all declared data files validated.
- Python: 12 files parsed and compiled without executing Odoo imports.
- XML: 8 files well formed; Odoo 19 list/modifier syntax, local IDs, view fields and object actions checked.
- All eight XML data files pass the official Odoo 19 import RelaxNG schema; invoice-form and bill/invoice-list inheritance XPath targets exist in the upstream views.
- Requested UI revision checked: split green/red decisions, notes-only popup, guarded Reset Bills, dedicated Bill/Invoice list-header buttons, and no Action-menu bindings.
- Approval History layout checked: summary block removed and Approval Route table shown first.
- Optional voucher payment checked: configuration boolean exists, Pay is limited to approved vouchers, and the backend object action is present.
- Partner rule checked: same-partner defaults on, may be disabled per config, company/currency remain mandatory, and mixed-partner summaries retain partner names.
- Invoice toolbar compatibility checked: button visibility accepts both default_move_type and search_default_out_invoice action contexts.
- Frontend fallback checked: Receive Voucher is injected into the generic Odoo list selection toolbar, restricted to Voucher Users and selected customer invoices.
- Pre-create confirmations checked: Vendor Bill XML and Customer Invoice list-controller actions both require explicit Proceed before calling the backend.
- Security: 17 ACL entries checked; snapshot/route/history ACLs readonly, company rules present for all persistent voucher models.
- Executed 10 offline policy tests successfully, including six cumulative threshold boundary cases.
- Compatibility contracts: payment method signatures, invoice link field, group privilege, server-action group field and parent menu IDs matched against downloaded Odoo 19.0 source.
- Workflow inspection: voucher engine contains no payment/journal-entry creation or reconciliation calls.

## Test output

```text
test_cumulative_threshold_boundaries (__main__.PolicyTests.test_cumulative_threshold_boundaries) ... ok
test_delegate_end_inclusive (__main__.PolicyTests.test_delegate_end_inclusive) ... ok
test_delegate_single_day (__main__.PolicyTests.test_delegate_single_day) ... ok
test_delegate_start_inclusive (__main__.PolicyTests.test_delegate_start_inclusive) ... ok
test_expired (__main__.PolicyTests.test_expired) ... ok
test_invalid_range (__main__.PolicyTests.test_invalid_range) ... ok
test_missing_dates (__main__.PolicyTests.test_missing_dates) ... ok
test_not_started (__main__.PolicyTests.test_not_started) ... ok
test_original_approver (__main__.PolicyTests.test_original_approver) ... ok
test_unrelated_user (__main__.PolicyTests.test_unrelated_user) ... ok

----------------------------------------------------------------------
Ran 10 tests in 0.000s

OK
```

## Not executed

The 19 bundled Odoo integration test methods were syntax-checked but not run. No Odoo server, Enterprise runtime or PostgreSQL instance was available. Registry loading, database constraints, view inheritance against the actual installed stack, UI behavior, record rules and end-to-end payments remain unverified until staging installation. Offline success is not a claim of production readiness.
