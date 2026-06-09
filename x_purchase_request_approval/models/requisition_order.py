# -*- coding: utf-8 -*-

from datetime import datetime
from odoo import api, fields, models, tools, _
from odoo.exceptions import ValidationError


class RequisitionOrder(models.Model):
    _name = 'requisition.order'
    _inherit = ['requisition.order', 'analytic.mixin']

    line_no = fields.Char(string='Line No')
    estimate_price = fields.Float(string='Estimate Price', required=True, digits='Product Price')
    total_price = fields.Monetary(compute='_compute_amount', string='Total Price', aggregator=None, store=True)
    currency_id = fields.Many2one(related='requisition_product_id.currency_id', store=True, string='Currency', readonly=True)
    remark = fields.Char(string='Remark')
    ordered_qty = fields.Integer('Ordered Qty')
    remaining_qty = fields.Integer('Remaining Qty')
    uom_id = fields.Many2one(comodel_name='uom.uom', string='Unit of Measure',
                             compute='_compute_uom_id', store=True, readonly=False, precompute=True,
                             help='Product unit of measure')
    
    @api.depends('product_id')
    def _compute_uom_id(self):
        for record in self:
            if record.product_id:
                record.uom_id = record.product_id.uom_id
            else:
                record.uom_id = False

    def check_quantity(self):
        # for line in self:
        #     if line.quantity <= 0:
        #         raise ValidationError(_('Quantity cannot be greater than zero.'))
        pass

    def add_remaining_qty(self):
        for line in self:
            line.remaining_qty = line.quantity

    @api.depends('quantity', 'estimate_price')
    def _compute_amount(self):
        for line in self:
            line.total_price = line.quantity * line.estimate_price