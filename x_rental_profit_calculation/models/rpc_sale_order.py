# -*- coding: utf-8 -*-
from odoo import fields, models


class RpcSaleOrder(models.Model):
    _inherit = 'sale.order'

    rpc_document_id = fields.Many2one(
        'rpc.document',
        string='RPC Document',
        copy=False,
        index=True,
        ondelete='set null',
    )

    _rpc_document_unique = models.Constraint(
        'UNIQUE(rpc_document_id)',
        'Setiap dokumen RPC hanya boleh memiliki satu quotation.',
    )
