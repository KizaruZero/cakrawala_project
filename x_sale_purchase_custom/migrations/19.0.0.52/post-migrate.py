from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    """Undo only this module's historical paperformat bindings, not user choices."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    paperformat = env.ref('x_sale_purchase_custom.paperformat_invoice_custom', raise_if_not_found=False)
    if not paperformat:
        return
    for xmlid in ('account.account_invoices', 'account.account_invoices_without_payment'):
        report = env.ref(xmlid, raise_if_not_found=False)
        if report and report.paperformat_id == paperformat:
            report.paperformat_id = False
