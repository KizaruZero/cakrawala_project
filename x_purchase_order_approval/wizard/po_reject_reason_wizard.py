# -*- coding: utf-8 -*-

# from odoo import fields, models, api, _
# from odoo.exceptions import UserError, ValidationError
# from odoo.addons import decimal_precision as dp
# from datetime import datetime
# from dateutil.relativedelta import relativedelta
from odoo import fields, models


class PoRejectReasonWizard(models.TransientModel):
    _name = 'po.reject.reason.wizard'
    _description = "Wizard in case of reject reasons"

    purchase_order_id = fields.Many2one('purchase.order')
    notes = fields.Text('Description')

    def action_confirm(self):
        ### write sebagai log note
        reject_reasons = "Reject reasons: " + self.notes
        self.purchase_order_id.message_post(body=reject_reasons, subtype_xmlid="mail.mt_note")
        self.purchase_order_id.button_reject()
        self.purchase_order_id.reject_reason = self.notes