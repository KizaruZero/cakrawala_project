from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    """Normalize the former wide incentive multiplier matrix."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    env['rpc.incentive.factor']._ensure_default_rules()
