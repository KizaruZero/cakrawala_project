import logging

from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Flag the standard "Replacement Car" sub-status as Is Replacement Car.

    Replacement Car logic used to find it by name; it now reads the flag. The
    standard sub-statuses are noupdate data, so the flag in the data file only
    reaches new databases. Left alone when a sub-status is already flagged.
    """
    env = api.Environment(cr, SUPERUSER_ID, {})
    Substatus = env['vehicle.substatus'].with_context(active_test=False)
    if Substatus.search_count([('is_replacement_car', '=', True)], limit=1):
        return
    substatus = env.ref('x_stock_asset_receipt.vehicle_substatus_replacement_car', raise_if_not_found=False)
    if not substatus:
        _logger.warning("No standard 'Replacement Car' sub-status: flag one as Is Replacement Car in Master Sub Status.")
        return
    substatus.is_replacement_car = True
    _logger.info("Sub-status %s (%s) flagged as Is Replacement Car.", substatus.id, substatus.name)
