# -*- coding: utf-8 -*-
from odoo import models, fields, api

class EmployeePurchaseRequisition(models.Model):
    _inherit = 'employee.purchase.requisition'

    sale_order_id = fields.Many2one('sale.order', string='Sales Order Related', readonly=True)
    customer_so_related = fields.Char(string='Customer SO Related', readonly=True)
    rental_type_id = fields.Many2one('sale.rental.type', string='Rental Type', readonly=True)
    rpc_id = fields.Many2one('rpc.document', string='RPC', compute='_compute_rpc_id', store=True, readonly=True)

    @api.depends('sale_order_id.opportunity_id')
    def _compute_rpc_id(self):
        for req in self:
            if req.sale_order_id and req.sale_order_id.opportunity_id:
                rpc_doc = self.env['rpc.document'].search([('crm_lead_id', '=', req.sale_order_id.opportunity_id.id)], order='id desc', limit=1)
                req.rpc_id = rpc_doc.id if rpc_doc else False
            else:
                req.rpc_id = False
