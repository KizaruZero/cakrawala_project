from odoo import api
from odoo.fields import Command


def _backfill_allowed_users(env):
    """Existing operation types get an empty M2M; default only runs on create."""
    admin = env.ref("base.user_admin", raise_if_not_found=False)
    if not admin:
        return
    empty_types = env["stock.picking.type"].search([]).filtered(
        lambda pt: not pt.allowed_user_ids
    )
    if empty_types:
        empty_types.write({"allowed_user_ids": [Command.link(admin.id)]})


def post_init_hook(env):
    _backfill_allowed_users(env)
