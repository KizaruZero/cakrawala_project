from odoo import api, fields, SUPERUSER_ID


def migrate(cr, version):
    """Backfill plate-history for documents that are still running.

    Before this version, the active plate-history segment was left with an empty
    valid_until while its document was open. Now valid_until must follow the
    Document Expiration Date and the active segment is identified by contract_id.

    For every open license-plate document, link its current plate's latest open
    history segment and set valid_until = expiration_date so already-running
    documents show the correct Valid Until without any manual re-save.
    """
    env = api.Environment(cr, SUPERUSER_ID, {})
    History = env['fleet.vehicle.license.plate.history']

    open_contracts = env['fleet.vehicle.log.contract'].search([
        ('state', '=', 'open'),
        ('cost_subtype_id.is_license_plate', '=', True),
        ('vehicle_id', '!=', False),
        ('license_plate', '!=', False),
    ])
    for contract in open_contracts:
        seg = History.search([
            ('vehicle_id', '=', contract.vehicle_id.id),
            ('license_plate', '=', contract.license_plate),
            ('contract_id', '=', False),
            ('valid_until', '=', False),
        ], order='id desc', limit=1)
        if not seg:
            continue
        vals = {'contract_id': contract.id}
        if contract.expiration_date:
            vals['valid_until'] = contract.expiration_date
        if not seg.valid_from and contract.start_date:
            vals['valid_from'] = contract.start_date
        seg.write(vals)
