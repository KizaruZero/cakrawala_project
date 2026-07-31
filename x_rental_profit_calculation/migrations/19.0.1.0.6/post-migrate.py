from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    documents = env['rpc.document'].search([])
    documents._compute_resale()
    documents._compute_catatan_rv()
