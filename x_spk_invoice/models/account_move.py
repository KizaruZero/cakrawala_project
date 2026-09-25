# -*- coding: utf-8 -*-
from odoo import models, fields, api

class AccountMove(models.Model):
    _inherit = 'account.move'

    fleet_spk_id = fields.Many2one(
        'fleet.spk',
        string='SPK Reference',
        copy=False,
        compute='_compute_fleet_spk_id',
        store=True,
        readonly=False,
    )

    @api.depends('invoice_line_ids.purchase_line_id.order_id.fleet_spk_id')
    def _compute_fleet_spk_id(self):
        for move in self:
            if not move.fleet_spk_id:
                spk = move.invoice_line_ids.purchase_line_id.order_id.fleet_spk_id
                if spk:
                    move.fleet_spk_id = spk[0]


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    item_type = fields.Selection([
        ('jasa', 'Jasa'),
        ('sparepart', 'Sparepart'),
    ], string='Jasa/Sparepart', compute='_compute_item_type', store=True, readonly=True)

    @api.depends('product_id', 'product_id.type')
    def _compute_item_type(self):
        for line in self:
            if line.product_id:
                if line.product_id.type == 'service':
                    line.item_type = 'jasa'
                else:
                    line.item_type = 'sparepart'
            elif not line.item_type:
                line.item_type = False


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    def _prepare_invoice(self):
        invoice_vals = super()._prepare_invoice()
        if self.fleet_spk_id:
            invoice_vals['fleet_spk_id'] = self.fleet_spk_id.id
        return invoice_vals
