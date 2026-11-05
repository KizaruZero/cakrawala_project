# -*- coding: utf-8 -*-
from odoo import _, models


class BastkManagement(models.Model):
    _inherit = 'bastk.management'

    def action_submit_outside(self):
        res = super().action_submit_outside()
        self.filtered(lambda bastk: bastk.state == 'submitted_outside')._sync_rental_actual_delivery()
        return res

    def action_submit_inside(self):
        res = super().action_submit_inside()
        for bastk in self.filtered(lambda bastk: bastk.state == 'submitted_inside').sudo():
            bastk._get_rental_unit_moves().sale_line_id.write({'bastk_return_date': bastk.end_date})
        return res

    def _get_rental_moves(self):
        """Moves of the deliveries of this BASTK made for a Rental Order."""
        self.ensure_one()
        deliveries = self._get_linked_pickings().filtered(lambda p: p.picking_type_code == 'outgoing')
        return deliveries.move_ids.filtered(
            lambda m: m.state != 'cancel' and m.sale_line_id.order_id.is_rental_order
        )

    def _get_rental_unit_moves(self):
        """The rental moves holding the vehicle of this BASTK."""
        return self._get_rental_moves().filtered(lambda m: self.vehicle_id.lot_id in m.move_line_ids.lot_id)

    def _sync_rental_actual_delivery(self):
        """Actual Delivery of a rental unit is the Tanggal Keluar of its BASTK.

        The sale line is reached through the delivery of the BASTK, on the move
        holding its vehicle: each line follows the BASTK of its own unit. The same
        unit delivered again on a line keeps the date its rental started from; a
        line that changes unit takes the date of the new unit. The unit is out
        again, so a Return Date of an earlier BASTK no longer applies.
        """
        for bastk in self.sudo():
            moves = bastk._get_rental_moves()
            unit_moves = bastk._get_rental_unit_moves()
            if moves and not unit_moves:
                bastk.message_post(body=_(
                    "Actual Delivery di Rental Order tidak terisi: vehicle BASTK ini "
                    "tidak sesuai dengan unit pada %(picking)s.",
                    picking=', '.join(moves.picking_id.mapped('name')),
                ))
            for line in unit_moves.sale_line_id:
                same_unit = line.move_ids.filtered(lambda m: m.state != 'cancel').bastk_unit_id.filtered(
                    lambda b: b.vehicle_id == bastk.vehicle_id and b.state != 'draft' and b.start_date
                )
                date = min((same_unit | bastk).mapped('start_date'))
                if line.actual_delivery_date != date:
                    line.actual_delivery_date = date
            unit_moves.sale_line_id.write({'bastk_return_date': False})
