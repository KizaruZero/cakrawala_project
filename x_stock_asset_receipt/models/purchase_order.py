from odoo import api, fields, models


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    fleet_vehicle_ids = fields.Many2many(
        'fleet.vehicle',
        string='Fleet / Vehicles',
        compute='_compute_fleet_vehicle_ids',
        help='Vehicles registered from the goods receipts of this purchase order.',
    )
    fleet_vehicle_count = fields.Integer(
        string='Fleet / Vehicle Count',
        compute='_compute_fleet_vehicle_ids',
    )

    @api.depends(
        'order_line.move_ids.state',
        'order_line.move_ids.picking_code',
        'order_line.move_ids.move_line_ids.lot_id.fleet_vehicle_id',
    )
    def _compute_fleet_vehicle_ids(self):
        """Vehicles received through this PO.

            order line -> stock.move (purchase_line_id) -> move line -> lot
            -> fleet.vehicle (lot_id)

        Going through the order lines rather than through a single picking means
        backorders are covered too: every receipt of the PO contributes its own
        units.
        """
        for order in self:
            moves = order.order_line.move_ids.filtered(
                lambda m: m.state == 'done'
                and m.picking_code == 'incoming'
                and m.product_id.is_vehicle
            )
            vehicles = moves.move_line_ids.lot_id.fleet_vehicle_id
            order.fleet_vehicle_ids = vehicles
            order.fleet_vehicle_count = len(vehicles)

    def action_view_fleet_vehicles(self):
        self.ensure_one()
        return self.fleet_vehicle_ids.action_open_fleet_vehicles()
