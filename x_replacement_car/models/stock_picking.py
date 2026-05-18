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

                substatus = self.env.ref(
                    "x_stock_asset_receipt.vehicle_substatus_replacement_car",
                    raise_if_not_found=False,
                )
                if substatus:
                    replacement.vehicle_old_id.write(
                        {"fleet_sub_status_id": substatus.id}
                    )

        return res