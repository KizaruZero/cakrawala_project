from odoo import models

class StockPicking(models.Model):
    _inherit = 'stock.picking'

    def button_validate(self):
        res = super().button_validate()

        for picking in self:

            replacement = self.env['replacement.car'].search([
                ('good_issue_id', '=', picking.id)
            ], limit=1)

            if replacement and picking.state == 'done':

                replacement_status = self.env['vehicle.substatus'].search([
                    ('name', '=', 'Replacement Car')
                ], limit=1)

                if replacement_status:

                    replacement.vehicle_old_id.write({
                        'fleet_sub_status_id': replacement_status.id,
                    })

                picking.move_ids.write({
                        'replacement_car': True,
                    })

        return res