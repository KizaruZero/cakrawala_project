from odoo import models

class StockPicking(models.Model):
    _inherit = 'stock.picking'

    def button_validate(self):
        res = super().button_validate()

        for picking in self:
            if picking.state != 'done':
                continue

            # Cek apakah DO ini terkait dengan Replacement Car
            replacement = self.env['replacement.car'].search([
                ('good_issue_id', '=', picking.id)
            ], limit=1)

            if not replacement:
                # DO ini bukan Good Issue dari RC — skip semua logic RC
                continue

            # ✅ Tandai semua move di DO ini sebagai replacement_car = True
            picking.move_ids.sudo().write({
                'replacement_car': True,
            })

            # ✅ Update Fleet Sub-Status kendaraan lama → "Replacement Car"
            replacement_status = self.env['vehicle.substatus'].search([
                ('name', '=', 'Replacement Car')
            ], limit=1)

            if replacement_status:
                replacement.vehicle_old_id.write({
                    'fleet_sub_status_id': replacement_status.id,
                })

        return res