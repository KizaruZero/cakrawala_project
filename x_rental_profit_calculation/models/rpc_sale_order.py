# -*- coding: utf-8 -*-
from odoo import api, fields, models


class RpcSaleOrder(models.Model):
    _inherit = 'sale.order'

    rpc_document_id = fields.Many2one(
        'rpc.document',
        string='RPC Document',
        copy=False,
        index=True,
        ondelete='set null',
    )
    rpc_document_ids = fields.Many2many(
        'rpc.document',
        'rpc_document_sale_order_rel',
        'sale_order_id',
        'rpc_document_id',
        string='RPC Documents',
        copy=False,
    )
    rpc_price_locked = fields.Boolean(
        string='RPC Unit Price Locked',
        compute='_compute_rpc_price_locked',
    )

    @api.depends('rpc_document_ids')
    def _compute_rpc_price_locked(self):
        for order in self:
            order.rpc_price_locked = bool(order.rpc_document_ids)

    _rpc_document_unique = models.Constraint(
        'UNIQUE(rpc_document_id)',
        'Setiap dokumen RPC hanya boleh memiliki satu quotation.',
    )
