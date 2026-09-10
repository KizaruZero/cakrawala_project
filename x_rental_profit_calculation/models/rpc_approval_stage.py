# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


RPC_APPROVAL_STATE_SELECTION = [
    ('submitted', 'Submitted'),
    ('procurement_done', 'Procurement Done'),
    ('operation_done', 'Operation Done'),
    ('finance_done', 'Finance Done'),
    ('approved', 'Approved'),
]


class RpcApprovalStage(models.Model):
    _name = 'rpc.approval.stage'
    _description = 'RPC Approval Stage'
    _order = 'sequence, id'

    name = fields.Char(string='Nama Tahap', required=True, translate=True)
    sequence = fields.Integer(string='Sequence', required=True, default=1)
    state = fields.Selection(
        RPC_APPROVAL_STATE_SELECTION,
        string='Status Tujuan',
        required=True,
    )
    approver_id = fields.Many2one(
        'res.users',
        string='Approver',
        required=True,
        default=lambda self: self.env.user,
        ondelete='restrict',
        domain=[('share', '=', False), ('active', '=', True)],
    )
    delegation_id = fields.Many2one(
        'res.users',
        string='Delegation',
        ondelete='restrict',
        domain=[('share', '=', False), ('active', '=', True)],
        help='User pengganti yang dapat melakukan approval pada tahap ini.',
    )
    active = fields.Boolean(default=True)

    _sequence_unique = models.Constraint(
        'UNIQUE(sequence)',
        'Sequence approval RPC harus unik!',
    )
    _state_unique = models.Constraint(
        'UNIQUE(state)',
        'Status tujuan hanya boleh digunakan oleh satu tahap approval RPC!',
    )

    @api.constrains('sequence')
    def _check_positive_sequence(self):
        for stage in self:
            if stage.sequence <= 0:
                raise ValidationError(_('Sequence harus lebih besar dari 0.'))

    @api.constrains('active', 'approver_id')
    def _check_active_approvers(self):
        for stage in self:
            if stage.active and not stage.approver_id:
                raise ValidationError(_(
                    'Tahap approval aktif harus memiliki Approver.'
                ))

    @api.constrains('approver_id', 'delegation_id')
    def _check_distinct_delegation(self):
        for stage in self:
            if (
                stage.approver_id
                and stage.delegation_id == stage.approver_id
            ):
                raise ValidationError(_(
                    'Delegation harus berbeda dengan Approver.'
                ))

    def _can_user_approve(self, user=None):
        """Authorize either the main approver or their delegation."""
        self.ensure_one()
        user = user or self.env.user
        return user in (self.approver_id | self.delegation_id)

    @api.model
    def _ensure_default_approvers(self):
        """Ensure every active stage has one approver without group lookup."""
        default_user = self.env.ref(
            'base.user_admin',
            raise_if_not_found=False,
        ) or self.env.user
        stages = self.with_context(active_test=False).search([
            ('approver_id', '=', False),
        ])
        for stage in stages:
            stage.approver_id = default_user
