# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

class PurchaseRequisition(models.Model):
    _inherit = 'purchase.requisition'

    def write(self, vals):
        if 'active' in vals and not vals['active']:
            for record in self:
                if record.state == 'draft':
                    raise ValidationError(_("You cannot archive a purchase agreement in Draft status. Please delete it instead."))
        return super(PurchaseRequisition, self).write(vals)
