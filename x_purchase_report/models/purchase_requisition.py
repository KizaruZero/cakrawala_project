# -*- coding: utf-8 -*-
###############################################################################
from odoo import api, fields, models
from odoo.exceptions import ValidationError


class PurchaseRequisitionInherit(models.Model):
    _inherit = 'employee.purchase.requisition'

    def action_print_report(self):
        """Print purchase requisition report"""
        data = {
            'employee': self.employee_id.name,
            'records': self,
            'order_ids': self.requisition_order_ids,
            'approval_ids': self.purchase_requisition_approver_matrix_ids,
            'currency': self.currency_id,
        }
        return (self.env.ref(
            'employee_purchase_requisition.'
            'action_report_purchase_requisition').report_action(
            self, data=data))
