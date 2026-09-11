# -*- coding: utf-8 -*-
from odoo import fields, models


class RpcDocumentApprovalMatrix(models.Model):
    _name = 'rpc.document.approval.matrix'
    _description = 'RPC Document Approval Matrix'
    _order = 'sequence, id'

    document_id = fields.Many2one(
        'rpc.document',
        string='Dokumen RPC',
        required=True,
        ondelete='cascade',
        index=True,
    )
    approval_stage_id = fields.Many2one(
        'rpc.approval.stage',
        string='Tahap Approval',
        required=True,
        ondelete='restrict',
        index=True,
    )
    sequence = fields.Integer(required=True, index=True)
    approver_id = fields.Many2one(
        'res.users',
        string='Approver',
        required=True,
        ondelete='restrict',
    )
    delegation_id = fields.Many2one(
        'res.users',
        string='Delegation',
        ondelete='restrict',
    )
    actual_approver_id = fields.Many2one(
        'res.users',
        string='Actual',
        ondelete='restrict',
        copy=False,
    )
    status = fields.Selection(
        [
            ('pending', 'Pending'),
            ('approved', 'Approved'),
            ('revised', 'Revised'),
        ],
        string='Status',
        required=True,
        default='pending',
        copy=False,
    )
    date_approved = fields.Datetime(string='Date Approved', copy=False)
    date_revised = fields.Datetime(string='Date Revised', copy=False)

    _document_stage_unique = models.Constraint(
        'UNIQUE(document_id, approval_stage_id)',
        'Tahap approval hanya dapat dicatat satu kali per dokumen RPC.',
    )