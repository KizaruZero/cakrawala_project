from odoo import api, SUPERUSER_ID

# Default Status / Sub-Status mapping (fleet_status.md). Keys: vehicle.substatus xml-ids.
DEFAULT_MAPPING = {
    'Leased': ['vehicle_substatus_short_term', 'vehicle_substatus_long_term'],
    'Non-Leased': [
        'vehicle_substatus_inventaris',
        'vehicle_substatus_re_marketing',
        'vehicle_substatus_replacement_car',
        'vehicle_substatus_disposal',
        'vehicle_substatus_total_loss_claim',
    ],
    'Inactive': ['vehicle_substatus_sold', 'vehicle_substatus_claim_closed'],
}


def migrate(cr, version):
    """Fill the Parent Status of the standard sub-statuses.

    Leased / Non-Leased / Inactive are configuration data without a reliable xml-id,
    so they are looked up by name (created when missing). Sub-statuses that already
    have a Parent Status are left untouched. Vehicles are not modified.
    """
    env = api.Environment(cr, SUPERUSER_ID, {})
    State = env['fleet.vehicle.state']
    for state_name, xmlids in DEFAULT_MAPPING.items():
        state = State.search([('name', '=', state_name)], limit=1) or State.create({'name': state_name})
        for xmlid in xmlids:
            sub = env.ref('x_stock_asset_receipt.%s' % xmlid, raise_if_not_found=False)
            if sub and not sub.state_id:
                sub.state_id = state
