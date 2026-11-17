"""19.0.1.0.11: lead time of running tickets counts up to today instead of staying 0."""

from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {'tz': 'Asia/Jakarta'})
    env['helpdesk.ticket'].cron_refresh_lead_time()
