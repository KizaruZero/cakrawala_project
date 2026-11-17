"""Recount Total Invoice and Tanggal Lunas of every SPK on customer invoices only.

Until 1.3 Create Invoice made a vendor bill, and the stored totals also counted the
vendor bills of the SPK PO. The SPK Service Report reads these stored fields.
"""

from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {"active_test": False})
    spks = env["fleet.spk"].search([])
    env.add_to_compute(spks._fields["total_invoice_amount"], spks)
    env.add_to_compute(spks._fields["paid_date"], spks)
    spks.flush_recordset(["total_invoice_amount", "paid_date"])
