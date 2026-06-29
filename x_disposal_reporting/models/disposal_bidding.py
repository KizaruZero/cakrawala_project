# -*- coding: utf-8 -*-
from odoo import models, fields, api

class DisposalBidding(models.Model):
    _inherit = 'disposal.bidding'

    vehicle_color = fields.Char(string='Warna', related='vehicle_id.color', store=True)
    vehicle_brand_name = fields.Char(string='Merk', related='vehicle_id.model_id.brand_id.name', store=True)
    vehicle_model_name = fields.Char(string='Tipe', related='vehicle_id.model_id.name', store=True)
    vehicle_sub_type = fields.Char(string='SubTipe', related='vehicle_id.sub_type', store=True)
    vehicle_model_year = fields.Char(string='Tahun', compute='_compute_vehicle_model_year', store=True)

    @api.depends('vehicle_id.model_year')
    def _compute_vehicle_model_year(self):
        for rec in self:
            rec.vehicle_model_year = str(rec.vehicle_id.model_year) if rec.vehicle_id and rec.vehicle_id.model_year else ''
