from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    """Fill the BPKB location of existing biddings: an approved one cannot be recomputed from its form."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    biddings = env['disposal.bidding'].with_context(active_test=False).search([
        ('disposal_bpkb_location', 'in', (False, '')),
    ])
    env.add_to_compute(biddings._fields['disposal_bpkb_location'], biddings)
    env.flush_all()
