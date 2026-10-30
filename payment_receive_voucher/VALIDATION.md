# Validation — v1.3.4

- Python sources parsed with Python AST.
- Manifest XML data parsed and validated against the Odoo 19 XML import schema.
- Report actions are bound to the Payment Voucher form Print menu, restricted to Voucher Users, and filtered to Payment Vouchers.
- ZIP integrity and versioned artifact paths checked; prior release archives remain untouched.
- Static checks only; no live Odoo database upgrade or UI verification was run.
- PDF rendering requires a working wkhtmltopdf 0.12.6 installation discoverable by Odoo. Without it, Odoo can fall back to HTML preview.
