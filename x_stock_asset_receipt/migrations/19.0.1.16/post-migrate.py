import logging

from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Flag the standard "Sold" and "Claim Closed" sub-statuses as Is Sold.

    The fleet lock used to follow the Inactive status; it now reads this flag. The
    standard sub-statuses are noupdate data, so the flag in the data file only reaches
    new databases. Left alone when a sub-status is already flagged.
    """
    env = api.Environment(cr, SUPERUSER_ID, {})
    Substatus = env['vehicle.substatus'].with_context(active_test=False)
    if Substatus.search_count([('is_sold', '=', True)], limit=1):
        return
    for xml_id in ('vehicle_substatus_sold', 'vehicle_substatus_claim_closed'):
        substatus = env.ref('x_stock_asset_receipt.%s' % xml_id, raise_if_not_found=False)
        if not substatus:
            _logger.warning("No standard %s sub-status: flag it as Is Sold in Master Sub Status.", xml_id)
            continue
        substatus.is_sold = True
        _logger.info("Sub-status %s (%s) flagged as Is Sold.", substatus.id, substatus.name)
