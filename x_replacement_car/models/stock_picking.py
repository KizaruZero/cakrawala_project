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

                replacement.vehicle_old_id.write({
                    #'fleet_sub_status': 'replacement_car'
                })

        return res