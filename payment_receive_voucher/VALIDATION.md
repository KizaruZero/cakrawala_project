# Validation — v1.4.8

- Python sources parsed with AST and XML files parsed for well-formedness.
- Manifest data paths checked against the module tree.
- ZIP root and archive integrity checked.
- Static validation only; no live Odoo 19 server was available.
- Print PV Summary Only uses its own A5 landscape paperformat and QWeb template without `web.external_layout`; Print PV Detail is unchanged.
