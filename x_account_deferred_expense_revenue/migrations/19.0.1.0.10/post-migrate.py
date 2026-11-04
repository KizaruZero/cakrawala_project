from odoo import api, SUPERUSER_ID


def migrate(cr, version):
    # Correct only the stored display state of historical cancelled journals.
    # No move, balance, date, name or historical entry status is rewritten.
    env = api.Environment(cr, SUPERUSER_ID, {})
    lines = env['account.deferred.entry.line'].search([('move_id.state', '=', 'cancel'), ('state', '!=', 'cancel')])
    lines._compute_state()
