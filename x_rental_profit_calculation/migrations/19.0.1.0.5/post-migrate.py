from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    env['rpc.document.stnk.line'].search([])._compute_amount()
    env['rpc.document.service.line'].search([])._compute_amount()
