# -*- coding: utf-8 -*-
from odoo import models, fields, api

class DisposalBidding(models.Model):
    _inherit = 'disposal.bidding'

    vehicle_color = fields.Char(string='Warna', related='vehicle_id.color', store=True)
    vehicle_brand_name = fields.Char(string='Merk', related='vehicle_id.model_id.brand_id.name', store=True)
    vehicle_model_name = fields.Char(string='Tipe', related='vehicle_id.model_id.name', store=True)
    vehicle_sub_type = fields.Char(string='SubTipe', related='vehicle_id.sub_type_id.name', store=True, translate=False)
    vehicle_model_year = fields.Char(string='Tahun', compute='_compute_vehicle_model_year', store=True)
    status_disposal_date = fields.Date(string='Status Disposal Date', related='vehicle_id.disposal_start_date')
    is_sale_fully_paid = fields.Boolean(
        string='Sale Fully Paid',
        compute='_compute_is_sale_fully_paid',
        compute_sudo=True,
        store=True,
        help='The sale order of this bidding is fully invoiced and every invoice is Paid.',
    )

    @api.depends(
        'sale_order_id.invoice_status',
        'sale_order_id.order_line.invoice_lines.move_id.state',
        'sale_order_id.order_line.invoice_lines.move_id.payment_state',
    )
    def _compute_is_sale_fully_paid(self):
        for rec in self:
            rec.is_sale_fully_paid = bool(rec.sale_order_id) and rec.sale_order_id._is_fully_paid()

    @api.depends('vehicle_id.model_year')
    def _compute_vehicle_model_year(self):
        for rec in self:
            rec.vehicle_model_year = str(rec.vehicle_id.model_year) if rec.vehicle_id and rec.vehicle_id.model_year else ''
