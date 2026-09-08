# -*- coding: utf-8 -*-


def migrate(cr, version):
    """Seed master-stage approvers from the former access groups once."""
    from odoo import api, SUPERUSER_ID

    env = api.Environment(cr, SUPERUSER_ID, {})
    env['rpc.approval.stage']._ensure_default_approvers()
