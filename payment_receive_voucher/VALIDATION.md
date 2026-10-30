# Validation — v1.3.10

- Python sources parsed with Python AST.
- Manifest XML data parsed and validated against the Odoo 19 XML import schema.
- Both Summary tables retain compact widths and no longer set a smaller custom font, matching the Bill Details table's inherited font size.
- ZIP integrity and versioned artifact paths checked; previous release archives remain untouched.
- Static checks only; no live Odoo database upgrade or PDF rendering was run.
