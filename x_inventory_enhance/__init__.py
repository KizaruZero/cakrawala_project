from . import models


def post_init_hook(env):
    env["stock.picking.type"]._set_default_allowed_admin()
