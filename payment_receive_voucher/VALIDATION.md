# Validation — v1.4.3

- All 17 Python sources parsed with Python AST.
- All 12 XML files are well-formed; all 11 XML data files listed in the manifest validate against the local Odoo 19 Relax NG schema.
- Confirmed the Pay wizard preserves Odoo grouping rules without a voucher configuration and enables grouped mode for voucher-backed multi-document partial amounts when configuration allows it.
- ZIP integrity and versioned artifact paths checked; previous release archives remain untouched.
- Static checks only; no live Odoo database upgrade, payment wizard run, or PDF rendering was performed.
