# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class EtApprovalDelegation(models.Model):
    _name = 'et.approval.delegation'
    _description = 'Early Termination Approval Delegation'
    _order = 'valid_from desc, id desc'

    group_id = fields.Many2one(
        'res.groups',
        string='Group',
        ondelete='cascade',
        required=True,
        default=lambda self: self.env.ref('x_sale_purchase_custom.group_et_director', raise_if_not_found=False),
        help='User group for Early Termination approval.',
    )
    delegate_user_id = fields.Many2one(
        'res.users',
        string='User Pengganti (Delegate)',
        required=True,
        domain=[('share', '=', False), ('active', '=', True)],
        help='User yang didelegasikan wewenang untuk menyetujui Early Termination.',
    )
    delegator_user_id = fields.Many2one(
        'res.users',
        string='Didelegasikan Oleh',
        default=lambda self: self.env.user,
        domain=[('share', '=', False), ('active', '=', True)],
        help='Direktur yang memberikan wewenang delegasi.',
    )
    valid_from = fields.Date(
        string='Valid From',
        required=True,
        default=fields.Date.context_today,
        help='Tanggal awal berlakunya delegasi approval.',
    )
    valid_until = fields.Date(
        string='Valid Until',
        required=True,
        help='Tanggal akhir berlakunya delegasi approval.',
    )
    notes = fields.Char(
        string='Catatan / Alasan',
        help='Catatan atau alasan pendelegasian wewenang approval.',
    )
    active = fields.Boolean(
        string='Aktif',
        default=True,
    )

    @api.constrains('valid_from', 'valid_until')
    def _check_validity_dates(self):
        for rec in self:
            if rec.valid_from and rec.valid_until and rec.valid_from > rec.valid_until:
                raise ValidationError(_('Valid Until tidak boleh lebih awal dari Valid From.'))

    @api.model
    def is_user_et_delegate(self, user=None, target_date=None):
        """Check if user has a valid active delegation for Early Termination approval."""
        if user is None:
            user = self.env.user
        if not user or user._is_public():
            return False
        date = target_date or fields.Date.context_today(self)
        et_group = self.env.ref('x_sale_purchase_custom.group_et_director', raise_if_not_found=False)
        if not et_group:
            return False
        domain = [
            ('group_id', '=', et_group.id),
            ('delegate_user_id', '=', user.id),
            ('active', '=', True),
            ('valid_from', '<=', date),
            ('valid_until', '>=', date),
        ]
        return bool(self.sudo().search_count(domain))

    @api.model
    def get_active_et_delegation(self, user=None, target_date=None):
        """Get the active delegation record for the given user if one exists."""
        if user is None:
            user = self.env.user
        if not user or user._is_public():
            return self.env['et.approval.delegation']
        date = target_date or fields.Date.context_today(self)
        et_group = self.env.ref('x_sale_purchase_custom.group_et_director', raise_if_not_found=False)
        if not et_group:
            return self.env['et.approval.delegation']
        domain = [
            ('group_id', '=', et_group.id),
            ('delegate_user_id', '=', user.id),
            ('active', '=', True),
            ('valid_from', '<=', date),
            ('valid_until', '>=', date),
        ]
        return self.sudo().search(domain, limit=1)


class ResGroups(models.Model):
    _inherit = 'res.groups'

    is_et_director_group = fields.Boolean(
        string='Is ET Director Group',
        compute='_compute_is_et_director_group',
    )
    et_delegation_ids = fields.One2many(
        'et.approval.delegation',
        'group_id',
        string='ET Approval Delegations',
    )

    def _compute_is_et_director_group(self):
        et_group = self.env.ref('x_sale_purchase_custom.group_et_director', raise_if_not_found=False)
        et_group_id = et_group.id if et_group else False
        for rec in self:
            rec.is_et_director_group = bool(et_group_id and rec.id == et_group_id)
