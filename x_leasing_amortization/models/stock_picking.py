# -*- coding: utf-8 -*-
from odoo import _, models


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    def _action_done(self):
        """Keep the Vehicle of the PO's leasing schedules in step with the GR.

        Runs after super(): x_stock_asset_receipt registers the received units
        as fleet vehicles there, so each Fleet Number already points at its
        vehicle when the leasing schedules are filled.
        """
        res = super()._action_done()
        self.move_ids.filtered(lambda m: m.state == 'done')._sync_leasing_vehicles()
        return res


class StockMove(models.Model):
    _inherit = 'stock.move'

    def _leasing_purchase_line(self):
        self.ensure_one()
        return self.purchase_line_id or self.origin_returned_move_id.purchase_line_id

    def _leasing_vehicles(self):
        """Vehicles moved here, in the order of the detail lines."""
        self.ensure_one()
        return self.move_line_ids.filtered(lambda ml: ml.quantity > 0).lot_id.fleet_vehicle_id

    def _sync_leasing_vehicles(self):
        """Fill the leasing Vehicle on a receipt, release it on a return to vendor."""
        for move in self.sorted('id'):
            line = move._leasing_purchase_line()
            if not line:
                continue
            if move._is_purchase_return():
                move._release_leasing_vehicles(line)
            elif move.picking_code == 'incoming':
                move._assign_leasing_vehicles(line)

    def _assign_leasing_vehicles(self, line):
        """Give each received unit to the first draft schedule of its PO line
        that has no Vehicle yet.

        Schedules created before they were linked to a PO line (no
        purchase_line_id) are matched by their Variant instead.
        """
        Loan = self.env['account.loan'].sudo()
        vehicles = self._leasing_vehicles()
        if not vehicles:
            return
        taken = Loan.search([
            ('vehicle_id', 'in', vehicles.ids),
            ('state', '!=', 'cancelled'),
        ]).vehicle_id
        free = Loan.search([
            ('purchase_order_id', '=', line.order_id.id),
            ('state', '=', 'draft'),
            ('vehicle_id', '=', False),
        ], order='id')
        variants = {line.name, line.product_id.display_name}
        candidates = list(
            free.filtered(lambda loan: loan.purchase_line_id == line)
            | free.filtered(lambda loan: not loan.purchase_line_id and loan.vehicle_variant in variants)
        )
        for vehicle in vehicles - taken:
            if not candidates:
                break
            candidates.pop(0).vehicle_id = vehicle

    def _release_leasing_vehicles(self, line):
        """A unit returned to the vendor no longer belongs to its schedule.

        A draft schedule is emptied so the replacement unit fills it on its
        receipt. A confirmed one already has journal entries: it is left as is
        and the return is reported in its chatter for Finance to follow up.
        """
        vehicles = self._leasing_vehicles()
        if not vehicles:
            return
        loans = self.env['account.loan'].sudo().search([
            ('purchase_order_id', '=', line.order_id.id),
            ('vehicle_id', 'in', vehicles.ids),
            ('state', '!=', 'cancelled'),
        ])
        for loan in loans:
            vehicle = loan.vehicle_id
            if loan.state == 'draft':
                loan.vehicle_id = False
                body = _(
                    "Vehicle %(vehicle)s dikosongkan karena unit diretur ke vendor (%(picking)s). "
                    "Akan terisi otomatis saat unit pengganti diterima.",
                    vehicle=vehicle.display_name, picking=self.picking_id.name,
                )
            else:
                body = _(
                    "Perhatian: Vehicle %(vehicle)s telah diretur ke vendor (%(picking)s), "
                    "sedangkan Leasing Schedule ini sudah berstatus %(state)s. "
                    "Mohon ditindaklanjuti oleh Finance.",
                    vehicle=vehicle.display_name, picking=self.picking_id.name,
                    state=dict(loan._fields['state'].selection).get(loan.state),
                )
            loan.message_post(body=body)
