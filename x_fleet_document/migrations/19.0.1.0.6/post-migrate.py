from odoo import api, SUPERUSER_ID


def migrate(cr, version):
    """Introduce «Is BPKB» on document types.

    The existing contract type named BPKB (which is not a license-plate type) is flagged,
    and its documents lose their expiration date so the expiry cron and reminders skip them.
    The vendor_id column is intentionally left in place: dropping the field keeps the data.
    """
    env = api.Environment(cr, SUPERUSER_ID, {})
    bpkb_types = env['fleet.service.type'].with_context(active_test=False).search([
        ('category', '=', 'contract'),
        ('is_license_plate', '=', False),
    ]).filtered(lambda t: (t.name or '').strip().upper() == 'BPKB')
    if not bpkb_types:
        return
    bpkb_types.write({'is_bpkb': True})
    docs = env['fleet.vehicle.log.contract'].with_context(active_test=False).search([
        ('cost_subtype_id', 'in', bpkb_types.ids),
        ('expiration_date', '!=', False),
    ])
    docs.write({'expiration_date': False})
