import logging

from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)

# Old selection value -> XML id of the seeded vehicle.substatus record it now points to.
RENTAL_TYPE_XIDS = {
    'short_term': 'x_stock_asset_receipt.vehicle_substatus_short_term',
    'long_term': 'x_stock_asset_receipt.vehicle_substatus_long_term',
}


def migrate(cr, version):
    """stock.picking.rental_type (selection) -> rental_type_id (m2o vehicle.substatus)."""
    env = api.Environment(cr, SUPERUSER_ID, {})

    # The two seeded rows live in a noupdate="1" block, so the data file cannot flag them
    # on an existing database — do it here instead.
    for xid in RENTAL_TYPE_XIDS.values():
        substatus = env.ref(xid, raise_if_not_found=False)
        if substatus:
            substatus.is_rental_type = True

    cr.execute(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_name = 'stock_picking' AND column_name = 'rental_type'"
    )
    if not cr.fetchone():
        return

    for old_value, xid in RENTAL_TYPE_XIDS.items():
        substatus = env.ref(xid, raise_if_not_found=False)
        if not substatus:
            _logger.warning("Missing %s, GRs with rental_type=%s keep no rental type", xid, old_value)
            continue
        cr.execute(
            "UPDATE stock_picking SET rental_type_id = %s "
            "WHERE rental_type = %s AND rental_type_id IS NULL",
            (substatus.id, old_value),
        )
        _logger.info("Migrated %s picking(s) with rental_type=%s", cr.rowcount, old_value)

    cr.execute("ALTER TABLE stock_picking DROP COLUMN rental_type")
