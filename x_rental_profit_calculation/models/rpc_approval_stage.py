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
    user_ids = fields.Many2many(
        'res.users',
        'rpc_approval_stage_user_rel',
        'stage_id',
        'user_id',
        string='Approver',
        required=True,
        domain=[('share', '=', False), ('active', '=', True)],
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

    @api.constrains('active', 'user_ids')
    def _check_active_approvers(self):
        for stage in self:
            if stage.active and not stage.user_ids:
                raise ValidationError(_(
                    'Tahap approval aktif harus memiliki minimal satu approver.'
                ))

    @api.model
    def _ensure_default_approvers(self):
        """Seed approvers once; later authorization reads only this master."""
        manager_group = self.env.ref(
            'x_rental_profit_calculation.group_rpc_manager',
            raise_if_not_found=False,
        )
        mappings = (
            (
                'rpc_approval_stage_submitted',
                'group_rpc_marketing',
            ),
            (
                'rpc_approval_stage_procurement_done',
                'group_rpc_procurement',
            ),
            (
                'rpc_approval_stage_operation_done',
                'group_rpc_operation',
            ),
            (
                'rpc_approval_stage_finance_done',
                'group_rpc_finance',
            ),
            (
                'rpc_approval_stage_approved',
                'group_rpc_finance',
            ),
        )
        for stage_xmlid, group_xmlid in mappings:
            stage = self.env.ref(
                f'x_rental_profit_calculation.{stage_xmlid}',
                raise_if_not_found=False,
            )
            group = self.env.ref(
                f'x_rental_profit_calculation.{group_xmlid}',
                raise_if_not_found=False,
            )
            if not stage:
                continue
            users = stage.user_ids
            if group:
                users |= group.user_ids
            if manager_group:
                users |= manager_group.user_ids
            if users != stage.user_ids:
                stage.user_ids = users
