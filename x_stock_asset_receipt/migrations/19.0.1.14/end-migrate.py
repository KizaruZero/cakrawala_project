import logging

from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Realign open fleet deliveries on their Fleet Number.

    Before 1.14 the analytic account shown on a delivery could be changed
    without the Fleet Number following, and a Fleet Number without analytic
    account kept the account of the unit chosen before. On open transfers the
    reserved Fleet Number wins: line data, line analytic account and the four
    move analytic fields are set from it.

    An end- script: it needs the fields of x_bastk_management / x_spk /
    x_disposal, loaded after this module.
    """
    env = api.Environment(cr, SUPERUSER_ID, {})
    moves = env['stock.move'].search([
        ('state', 'not in', ('draft', 'done', 'cancel')),
        ('product_id.is_vehicle', '=', True),
        ('picking_type_id.code', '!=', 'incoming'),
        ('move_line_ids.lot_id', '!=', False),
    ])

    def snapshot(move):
        return (
            move.x_asset_analytic_distribution,
            move.x_spk_analytic_distribution if 'x_spk_analytic_distribution' in move._fields else None,
            move.analytic_account_id.id if 'analytic_account_id' in move._fields else None,
            move.move_line_ids.mapped(lambda l: (l.analytic_account_id.id, l.chassis_number)),
        )

    for move in moves.filtered(lambda m: m._is_fleet_delivery_move()):
        before = snapshot(move)
        move.move_line_ids._sync_vehicle_fields_from_lot()
        after = snapshot(move)
        if before != after:
            _logger.info(
                "Fleet delivery %s (move %s, %s): realigned on Fleet Number %s: %s -> %s",
                move.picking_id.name, move.id, move.product_id.display_name,
                ', '.join(move.move_line_ids.lot_id.mapped('name')), before, after,
            )
