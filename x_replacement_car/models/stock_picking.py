from odoo import models

class StockPicking(models.Model):
    _inherit = 'stock.picking'

    def button_validate(self):
        res = super().button_validate()

        for picking in self:
            if picking.state != 'done':
                continue

            replacement = False
            if hasattr(picking, 'bastk_id') and picking.bastk_id and hasattr(picking.bastk_id, 'replacement_car_id'):
                replacement = picking.bastk_id.replacement_car_id

            if not replacement:
                continue

            picking.move_ids.sudo().write({
                'replacement_car': True,
            })

            # Goods Issue of the replacement unit to the customer: that unit (not the
            # broken one) becomes "Replacement Car"; its status follows the mapping.
            if picking.picking_type_code != 'outgoing' or not replacement.vehicle_new_id:
                continue
            replacement_status = self.env['vehicle.substatus']._get_replacement_car_substatus()

            if replacement_status:
                replacement.vehicle_new_id._set_fleet_status(sub_status=replacement_status)

        return res