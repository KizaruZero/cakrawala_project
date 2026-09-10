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
        'order_line.move_ids.move_line_ids.lot_id',
    )
    def _compute_fleet_vehicle_ids(self):
        """Vehicles received through this PO.

        Fleet has no foreign key back to purchasing: the bridge is the Fleet
        Number, carried as stock.lot.name on the receipt and copied to
        fleet.vehicle.asset_number when the unit is registered. Walk it the same
        way the PO report SQL view does:

            order line -> stock.move (purchase_line_id) -> move line -> lot
            -> fleet.vehicle.asset_number

        Going through the order lines rather than through a single picking means
        backorders are covered too: every receipt of the PO contributes its own
        units.
        """
        FleetVehicle = self.env['fleet.vehicle']
        for order in self:
            moves = order.order_line.move_ids.filtered(
                lambda m: m.state == 'done'
                and m.picking_code == 'incoming'
                and m.product_id.is_vehicle
            )
            asset_numbers = [
                name for name in moves.move_line_ids.lot_id.mapped('name') if name
            ]
            vehicles = FleetVehicle
            if asset_numbers:
                # Fleet Numbers come from a per-company sequence, so the same
                # number may exist in another company — keep this PO's company.
                vehicles = FleetVehicle.search([
                    ('asset_number', 'in', asset_numbers),
                    ('company_id', 'in', [order.company_id.id, False]),
                ])
            order.fleet_vehicle_ids = vehicles
            order.fleet_vehicle_count = len(vehicles)

    def action_view_fleet_vehicles(self):
        self.ensure_one()
        return self.fleet_vehicle_ids.action_open_fleet_vehicles()
