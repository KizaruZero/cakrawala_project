"""19.0.1.0.9: the new Completed stage is used by every existing Helpdesk team."""

from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    env['helpdesk.stage']._link_completed_stage_to_teams()
