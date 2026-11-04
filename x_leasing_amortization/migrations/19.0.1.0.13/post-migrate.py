from odoo import api, SUPERUSER_ID


def migrate(cr, version):
    """Refresh only Draft quote summaries, never schedules or posted history."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    loans = env['account.loan'].search([
        ('use_rate_conversion', '=', True), ('schedule_source', '=', 'compute'), ('state', '=', 'draft'),
    ])
    loans.filtered(lambda loan: not loan._flat_has_transactions())._compute_total_bunga()
