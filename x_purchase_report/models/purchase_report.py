from datetime import datetime

from babel.dates import format_date
from odoo import fields, models
from odoo.exceptions import UserError

class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    def _po_report_date(self, value):
        if not value:
            return ''
        if isinstance(value, datetime):
            value = fields.Datetime.context_timestamp(self, value).date()
        return format_date(value, 'dd MMMM yyyy', locale='id_ID')

    def _po_report_lines(self):
        self.ensure_one()
        return self.order_line.filtered(
            lambda line: not line.display_type
            and not line.is_downpayment
            and line.product_qty != 0
            and (line.product_id.name or '').strip().casefold() != 'down payment'
        )

    def action_print_custom(self):
        if not self:
            raise UserError("No record selected to print.")

        report = self.env.ref('x_purchase_report.report_purchase_order_custom_action')
        if not report:
            raise UserError("Custom report not found. Please check module.")
        
        return report.report_action(self)
