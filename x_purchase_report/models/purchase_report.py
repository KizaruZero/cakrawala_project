from odoo import models
from odoo.exceptions import UserError

class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    def action_print_custom(self):
        if not self:
            raise UserError("No record selected to print.")

        report = self.env.ref('x_purchase_report.report_purchase_order_custom_action')
        if not report:
            raise UserError("Custom report not found. Please check module.")
        
        return report.report_action(self)