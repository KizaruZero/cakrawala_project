import logging
from collections import Counter, defaultdict

from odoo import api, SUPERUSER_ID

from odoo.addons.x_stock_asset_receipt.models.stock_lot import FLEET_LOT_SYNC

_logger = logging.getLogger(__name__)

# Candidate lots per unlinked vehicle: same name as its Asset Number, a fleet
# product, and the vehicle's company or none. `received` tells same-named lots
# apart: only one of them was actually received on a validated goods receipt.
_CANDIDATES_SQL = """
    WITH candidate AS (
        SELECT fv.id AS vehicle_id,
               sl.id AS lot_id,
               EXISTS (
                   SELECT 1
                   FROM stock_move_line sml
                   JOIN stock_picking sp
                     ON sp.id = sml.picking_id AND sp.state = 'done'
                   JOIN stock_picking_type spt
                     ON spt.id = sp.picking_type_id AND spt.code = 'incoming'
                   WHERE sml.lot_id = sl.id
               ) AS received
        FROM fleet_vehicle fv
        JOIN stock_lot sl
          ON sl.name = fv.asset_number
         AND (sl.company_id = fv.company_id OR sl.company_id IS NULL OR fv.company_id IS NULL)
        JOIN product_product pp ON pp.id = sl.product_id
        JOIN product_template pt ON pt.id = pp.product_tmpl_id AND pt.is_vehicle
        WHERE COALESCE(fv.asset_number, '') <> ''
          AND fv.lot_id IS NULL
    )
    SELECT vehicle_id,
           array_agg(lot_id ORDER BY lot_id),
           array_agg(lot_id ORDER BY lot_id) FILTER (WHERE received)
    FROM candidate
    GROUP BY vehicle_id
"""


def resolve_vehicle_lots(cr):
    """Pair existing vehicles with their Fleet Number lot, without guessing.

    Returns ``(pairs, report)``: ``pairs`` maps vehicle id -> lot id for every
    vehicle resolved to exactly one free lot; ``report`` maps each outcome to its
    ``(vehicle id, candidate lot ids)`` rows. Read-only, so it doubles as a dry run.
    """
    cr.execute("SELECT lot_id FROM fleet_vehicle WHERE lot_id IS NOT NULL")
    taken = {row[0] for row in cr.fetchall()}

    report = defaultdict(list)
    cr.execute("SELECT id FROM fleet_vehicle WHERE COALESCE(asset_number, '') = '' AND lot_id IS NULL")
    report['no_asset_number'] = [(row[0], []) for row in cr.fetchall()]
    cr.execute("SELECT id FROM fleet_vehicle WHERE COALESCE(asset_number, '') <> '' AND lot_id IS NULL")
    with_asset_number = [row[0] for row in cr.fetchall()]

    chosen = {}
    cr.execute(_CANDIDATES_SQL)
    for vehicle_id, lots, received_lots in cr.fetchall():
        if len(lots) == 1:
            chosen[vehicle_id] = (lots[0], 'unique')
        elif received_lots and len(received_lots) == 1:
            chosen[vehicle_id] = (received_lots[0], 'received')
        else:
            report['ambiguous'].append((vehicle_id, lots))

    seen = set(chosen) | {vehicle_id for vehicle_id, _lots in report['ambiguous']}
    report['waiting_for_lot'] = [(vid, []) for vid in with_asset_number if vid not in seen]

    claims = Counter(lot_id for lot_id, _how in chosen.values())
    pairs = {}
    for vehicle_id, (lot_id, how) in chosen.items():
        if claims[lot_id] > 1 or lot_id in taken:
            report['conflict'].append((vehicle_id, [lot_id]))
        else:
            pairs[vehicle_id] = lot_id
            report[how].append((vehicle_id, [lot_id]))
    return pairs, report


def _report_duplicate_fleet_numbers(cr):
    """Fleet Numbers used twice in one company — not allowed from now on."""
    cr.execute("""
        SELECT sl.name, sl.company_id, array_agg(sl.id ORDER BY sl.id)
        FROM stock_lot sl
        JOIN product_product pp ON pp.id = sl.product_id
        JOIN product_template pt ON pt.id = pp.product_tmpl_id AND pt.is_vehicle
        GROUP BY sl.name, sl.company_id
        HAVING count(*) > 1
    """)
    for name, company_id, lot_ids in cr.fetchall():
        _logger.warning(
            "Fleet Number %s is used by several lots in company %s: %s — keep one, rename the others.",
            name, company_id, lot_ids,
        )


def _clean_analytic_accounts(cr):
    """Undo what the old name-based sync left on the analytic side.

    - An unlinked fleet lot holding the analytic account of a vehicle linked to
      another lot got it from that vehicle by name matching: cleared (the
      analytic account of a lot only ever comes from its own vehicle).
    - Vehicles sharing one analytic account, or holding one of another company,
      are only reported: fixing them means creating a new account.
    """
    cr.execute("""
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'fleet_vehicle' AND column_name = 'analytic_account_id'
    """)
    if not cr.fetchone():
        return
    cr.execute("""
        UPDATE stock_lot sl
           SET analytic_account_id = NULL
          FROM fleet_vehicle owner
         WHERE owner.analytic_account_id = sl.analytic_account_id
           AND owner.lot_id IS NOT NULL
           AND owner.lot_id <> sl.id
           AND NOT EXISTS (SELECT 1 FROM fleet_vehicle me WHERE me.lot_id = sl.id)
     RETURNING sl.id, sl.name, owner.id
    """)
    for lot_id, name, vehicle_id in cr.fetchall():
        _logger.warning(
            "stock.lot %s (%s): analytic account of vehicle %s removed — it was copied by name matching.",
            lot_id, name, vehicle_id,
        )
    cr.execute("""
        SELECT fv.analytic_account_id, array_agg(fv.id ORDER BY fv.id)
        FROM fleet_vehicle fv
        WHERE fv.analytic_account_id IS NOT NULL
        GROUP BY fv.analytic_account_id
        HAVING count(*) > 1
    """)
    for account_id, vehicle_ids in cr.fetchall():
        _logger.warning(
            "Analytic account %s is shared by vehicles %s — give each vehicle its own account.",
            account_id, vehicle_ids,
        )
    cr.execute("""
        SELECT fv.id, fv.company_id, aa.id, aa.company_id
        FROM fleet_vehicle fv
        JOIN account_analytic_account aa ON aa.id = fv.analytic_account_id
        WHERE aa.company_id IS NOT NULL AND fv.company_id IS NOT NULL
          AND aa.company_id <> fv.company_id
    """)
    for vehicle_id, company_id, account_id, account_company_id in cr.fetchall():
        _logger.warning(
            "Vehicle %s (company %s) uses analytic account %s of company %s.",
            vehicle_id, company_id, account_id, account_company_id,
        )


def _company_prefix_for_fleet_numbers(env):
    """Give every company its own Fleet Number prefix.

    Company sequences sharing one prefix produced the same Fleet Number in two
    companies. %(company_code)s is interpolated by x_stock_asset_receipt's
    ir.sequence override.
    """
    sequences = env['ir.sequence'].search([
        ('code', '=', 'asset.serial.number'),
        ('company_id', '!=', False),
    ])
    for sequence in sequences:
        prefix = sequence.prefix or ''
        if '%(company_code)s' in prefix:
            continue
        company = sequence.company_id
        if not (getattr(company, 'company_code', False) or company.code):
            _logger.warning(
                "Sequence %s (company %s) kept prefix %r: the company has no Company Code.",
                sequence.id, sequence.company_id.name, prefix,
            )
            continue
        new_prefix = prefix.replace('%(year)s', '%(company_code)s/%(year)s', 1) \
            if '%(year)s' in prefix else prefix + '%(company_code)s/'
        sequence.prefix = new_prefix
        _logger.info(
            "Sequence %s (company %s): Fleet Number prefix %r -> %r",
            sequence.id, sequence.company_id.name, prefix, new_prefix,
        )


def migrate(cr, version):
    """Link existing vehicles to their Fleet Number (fleet.vehicle.lot_id).

    Pairs found without ambiguity are linked and aligned (the vehicle's data has
    priority over the lot's). Everything else stays unlinked and is reported in
    the log and in the vehicle's chatter for manual follow-up.
    """
    env = api.Environment(cr, SUPERUSER_ID, {})
    pairs, report = resolve_vehicle_lots(cr)

    Vehicle = env['fleet.vehicle'].with_context(active_test=False)
    linked = Vehicle.browse()
    for vehicle_id, lot_id in pairs.items():
        vehicle = Vehicle.browse(vehicle_id)
        vehicle.with_context(**{FLEET_LOT_SYNC: True}).write({'lot_id': lot_id})
        linked |= vehicle
    linked._merge_with_linked_lot()

    for outcome, rows in sorted(report.items()):
        _logger.info("fleet.vehicle Fleet Number link — %s: %d vehicle(s)", outcome, len(rows))
    Lot = env['stock.lot']
    for outcome in ('ambiguous', 'conflict'):
        for vehicle_id, lot_ids in report[outcome]:
            lots = Lot.browse(lot_ids)
            _logger.warning(
                "fleet.vehicle %s left unlinked (%s), candidate lots: %s",
                vehicle_id, outcome, lot_ids,
            )
            Vehicle.browse(vehicle_id).message_post(body=(
                "Fleet Number not linked automatically (%s). Candidate lots: %s. "
                "Pick the right one in the Fleet Number field."
            ) % (outcome, ', '.join('%s [%s]' % (lot.name, lot.product_id.display_name) for lot in lots)))
    for vehicle_id, _lots in report['waiting_for_lot']:
        _logger.info("fleet.vehicle %s waits for its Fleet Number lot (none exists yet).", vehicle_id)

    env.flush_all()
    _report_duplicate_fleet_numbers(cr)
    _clean_analytic_accounts(cr)
    _company_prefix_for_fleet_numbers(env)
    env.invalidate_all()
