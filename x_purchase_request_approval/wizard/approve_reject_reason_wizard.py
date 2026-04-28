# -*- coding: utf-8 -*-

# from odoo import fields, models, api, _
# from odoo.exceptions import UserError, ValidationError
# from odoo.addons import decimal_precision as dp
# from datetime import datetime
# from dateutil.relativedelta import relativedelta
from odoo import fields, models


class PrRejectReasonWizard(models.TransientModel):
    _name = 'pr.reject.reason.wizard'
    _description = "Wizard in case of reject reasons"

    employee_purchase_requisition_id = fields.Many2one('employee.purchase.requisition')
    notes = fields.Text('Description')

    def action_confirm(self):
        ### write sebagai log note
        reject_reasons = "Reject reasons: " + self.notes
        self.employee_purchase_requisition_id.message_post(body=reject_reasons, subtype_xmlid="mail.mt_note")
        self.employee_purchase_requisition_id.button_reject()

class PrApproveWizard(models.TransientModel):
    _name = 'pr.approve.wizard'
    _description = "Wizard in case of approve"

    employee_purchase_requisition_id = fields.Many2one('employee.purchase.requisition')
    notes = fields.Text('Description')

    def action_confirm(self):
        if self.notes:
            ### write sebagai log note
            approve_notes = "Approve notes: " + self.notes
            self.employee_purchase_requisition_id.message_post(body=approve_notes, subtype_xmlid="mail.mt_note")
        self.employee_purchase_requisition_id.button_approve()