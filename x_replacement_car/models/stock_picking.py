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

            replacement_status = self.env['vehicle.substatus'].search([
                ('name', '=', 'Replacement Car')
            ], limit=1)

            if replacement_status:
                replacement.vehicle_old_id.write({
                    'fleet_sub_status_id': replacement_status.id,
                })

        return res