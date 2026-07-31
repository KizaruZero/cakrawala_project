# -*- coding: utf-8 -*-
from odoo import models, fields


class RentalOrderWizardLine(models.TransientModel):
    _inherit = 'rental.order.wizard.line'

    def _apply(self):
        """Override to auto-populate actual_delivery_date on sale.order.line when Pickup is validated."""
        res = super()._apply()
        for wizard_line in self:
            if wizard_line.status == 'pickup' and wizard_line.qty_delivered > 0:
                order_line = wizard_line.order_line_id
                if order_line and not order_line.actual_delivery_date:
                    order_line.actual_delivery_date = fields.Date.today()
        return res
