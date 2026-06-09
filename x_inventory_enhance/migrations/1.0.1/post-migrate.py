from odoo import api


def migrate(cr, version):
    env = api.Environment(cr, 1, {})
    from odoo.addons.x_inventory_enhance.hooks import _backfill_allowed_users

    _backfill_allowed_users(env)
