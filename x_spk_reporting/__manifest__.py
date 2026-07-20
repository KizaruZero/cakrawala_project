{
    "name": "SPK Service Reporting",
    "version": "19.0.1.0.0",
    "category": "Fleet Custom",
    "summary": "SPK service reporting list and printout",
    "author": "Cakrawala",
    "license": "LGPL-3",
    "depends": [
        "x_spk",
        # Total Invoice & Tanggal Lunas dibaca dari kolom yang ditambahkan modul ini
        # ke fleet_spk, jadi harus sudah ada sebelum SQL view dibuat.
        "x_spk_invoice",
    ],
    "data": [
        "security/ir.model.access.csv",
        "views/spk_service_report_views.xml",
        "report/spk_service_report_templates.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
}
