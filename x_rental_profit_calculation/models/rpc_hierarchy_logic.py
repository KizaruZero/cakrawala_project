# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class RpcHierarchyLogicHierarchy(models.Model):
    _name = 'rpc.hierarchy.logic.hierarchy'
    _description = 'RPC Hierarchy Logic Hierarchy Master'
    _order = 'sequence, name, id'

    name = fields.Char(string='Hierarchy', required=True)
    sequence = fields.Integer(string='Urutan', default=10)
    active = fields.Boolean(string='Aktif', default=True)
    cost_group_code_ids = fields.One2many(
        'rpc.hierarchy.logic.cost.group.code', 'hierarchy_id',
        string='Cost Group Code',
    )
    logic_ids = fields.One2many(
        'rpc.hierarchy.logic', 'hierarchy_id', string='Hierarchy Logic Table'
    )

    _name_unique = models.Constraint(
        'UNIQUE(name)',
        'Nama Hierarchy harus unik!',
    )


class RpcHierarchyLogicCostGroupCode(models.Model):
    _name = 'rpc.hierarchy.logic.cost.group.code'
    _description = 'RPC Hierarchy Logic Cost Group Code Master'
    _order = 'sequence, name, id'

    name = fields.Char(string='Cost Group Code', required=True)
    hierarchy_id = fields.Many2one(
        'rpc.hierarchy.logic.hierarchy',
        string='Hierarchy',
        required=True,
        ondelete='restrict',
        index=True,
    )
    sequence = fields.Integer(string='Urutan', default=10)
    active = fields.Boolean(string='Aktif', default=True)
    cost_group_name_ids = fields.One2many(
        'rpc.hierarchy.logic.cost.group.name', 'cost_group_code_id',
        string='Cost Group Name',
    )
    logic_ids = fields.One2many(
        'rpc.hierarchy.logic', 'cost_group_code_id',
        string='Hierarchy Logic Table',
    )

    _name_unique = models.Constraint(
        'UNIQUE(hierarchy_id, name)',
        'Cost Group Code harus unik pada setiap Hierarchy!',
    )

    @api.constrains('hierarchy_id')
    def _check_logic_hierarchy(self):
        if self.env.context.get('skip_hierarchy_chain_check'):
            return
        for record in self:
            invalid_logic = self.env['rpc.hierarchy.logic'].with_context(
                active_test=False
            ).search_count([
                ('cost_group_code_id', '=', record.id),
                ('hierarchy_id', '!=', record.hierarchy_id.id),
            ])
            if invalid_logic:
                raise ValidationError(_(
                    'Hierarchy pada Cost Group Code %s tidak boleh diubah karena '
                    'sudah digunakan pada Hierarchy Logic Table.',
                    record.display_name,
                ))


class RpcHierarchyLogicCostGroupName(models.Model):
    _name = 'rpc.hierarchy.logic.cost.group.name'
    _description = 'RPC Hierarchy Logic Cost Group Name Master'
    _order = 'sequence, name, id'

    name = fields.Char(string='Cost Group Name', required=True)
    cost_group_code_id = fields.Many2one(
        'rpc.hierarchy.logic.cost.group.code',
        string='Cost Group Code',
        required=True,
        ondelete='restrict',
        index=True,
    )
    sequence = fields.Integer(string='Urutan', default=10)
    active = fields.Boolean(string='Aktif', default=True)
    payment_schedule_ids = fields.One2many(
        'rpc.hierarchy.logic.payment.schedule', 'cost_group_name_id',
        string='Jadwal Pembayaran',
    )
    logic_ids = fields.One2many(
        'rpc.hierarchy.logic', 'cost_group_name_id',
        string='Hierarchy Logic Table',
    )

    _name_unique = models.Constraint(
        'UNIQUE(cost_group_code_id, name)',
        'Cost Group Name harus unik pada setiap Cost Group Code!',
    )

    @api.constrains('cost_group_code_id')
    def _check_logic_cost_group_code(self):
        if self.env.context.get('skip_hierarchy_chain_check'):
            return
        for record in self:
            invalid_logic = self.env['rpc.hierarchy.logic'].with_context(
                active_test=False
            ).search_count([
                ('cost_group_name_id', '=', record.id),
                ('cost_group_code_id', '!=', record.cost_group_code_id.id),
            ])
            if invalid_logic:
                raise ValidationError(_(
                    'Cost Group Code pada Cost Group Name %s tidak boleh diubah '
                    'karena sudah digunakan pada Hierarchy Logic Table.',
                    record.display_name,
                ))


class RpcHierarchyLogicPaymentSchedule(models.Model):
    _name = 'rpc.hierarchy.logic.payment.schedule'
    _description = 'RPC Hierarchy Logic Payment Schedule Master'
    _order = 'sequence, name, id'

    name = fields.Char(string='Jadwal Pembayaran', required=True)
    cost_group_name_id = fields.Many2one(
        'rpc.hierarchy.logic.cost.group.name',
        string='Cost Group Name',
        required=True,
        ondelete='restrict',
        index=True,
    )
    sequence = fields.Integer(string='Urutan', default=10)
    active = fields.Boolean(string='Aktif', default=True)
    logic_ids = fields.One2many(
        'rpc.hierarchy.logic', 'payment_schedule_id',
        string='Hierarchy Logic Table',
    )

    _name_unique = models.Constraint(
        'UNIQUE(cost_group_name_id, name)',
        'Jadwal Pembayaran harus unik pada setiap Cost Group Name!',
    )

    @api.constrains('cost_group_name_id')
    def _check_logic_cost_group_name(self):
        if self.env.context.get('skip_hierarchy_chain_check'):
            return
        for record in self:
            invalid_logic = self.env['rpc.hierarchy.logic'].with_context(
                active_test=False
            ).search_count([
                ('payment_schedule_id', '=', record.id),
                ('cost_group_name_id', '!=', record.cost_group_name_id.id),
            ])
            if invalid_logic:
                raise ValidationError(_(
                    'Cost Group Name pada Jadwal Pembayaran %s tidak boleh diubah '
                    'karena sudah digunakan pada Hierarchy Logic Table.',
                    record.display_name,
                ))


class RpcHierarchyLogic(models.Model):
    _name = 'rpc.hierarchy.logic'
    _description = 'RPC Hierarchy Logic Table'
    _order = 'sequence, id'
    _rec_name = 'cost_group_code_id'

    sequence = fields.Integer(string='Urutan', default=10)
    hierarchy_id = fields.Many2one(
        'rpc.hierarchy.logic.hierarchy',
        string='Hierarchy',
        required=True,
        ondelete='restrict',
        index=True,
    )
    cost_group_code_id = fields.Many2one(
        'rpc.hierarchy.logic.cost.group.code',
        string='Cost Group Code',
        required=True,
        ondelete='restrict',
        index=True,
    )
    cost_group_name_id = fields.Many2one(
        'rpc.hierarchy.logic.cost.group.name',
        string='Cost Group Name',
        required=True,
        ondelete='restrict',
        index=True,
    )
    payment_schedule_id = fields.Many2one(
        'rpc.hierarchy.logic.payment.schedule',
        string='Jadwal Pembayaran',
        required=True,
        ondelete='restrict',
        index=True,
    )
    formula = fields.Char(string='Formula')
    active = fields.Boolean(string='Aktif', default=True)

    _cost_group_code_unique = models.Constraint(
        'UNIQUE(cost_group_code_id)',
        'Cost Group Code hanya boleh digunakan satu kali pada Hierarchy Logic Table!',
    )

    @api.onchange('hierarchy_id')
    def _onchange_hierarchy_id(self):
        for record in self:
            if (
                record.cost_group_code_id
                and record.cost_group_code_id.hierarchy_id != record.hierarchy_id
            ):
                record.cost_group_code_id = False
                record.cost_group_name_id = False
                record.payment_schedule_id = False

    @api.onchange('cost_group_code_id')
    def _onchange_cost_group_code_id(self):
        for record in self:
            if (
                record.cost_group_name_id
                and record.cost_group_name_id.cost_group_code_id
                != record.cost_group_code_id
            ):
                record.cost_group_name_id = False
                record.payment_schedule_id = False

    @api.onchange('cost_group_name_id')
    def _onchange_cost_group_name_id(self):
        for record in self:
            if (
                record.payment_schedule_id
                and record.payment_schedule_id.cost_group_name_id
                != record.cost_group_name_id
            ):
                record.payment_schedule_id = False

    @api.constrains(
        'hierarchy_id', 'cost_group_code_id', 'cost_group_name_id',
        'payment_schedule_id',
    )
    def _check_hierarchy_chain(self):
        for record in self:
            if record.cost_group_code_id.hierarchy_id != record.hierarchy_id:
                raise ValidationError(_(
                    'Cost Group Code harus berasal dari Hierarchy yang dipilih.'
                ))
            if (
                record.cost_group_name_id.cost_group_code_id
                != record.cost_group_code_id
            ):
                raise ValidationError(_(
                    'Cost Group Name harus berasal dari Cost Group Code yang dipilih.'
                ))
            if (
                record.payment_schedule_id.cost_group_name_id
                != record.cost_group_name_id
            ):
                raise ValidationError(_(
                    'Jadwal Pembayaran harus berasal dari Cost Group Name yang dipilih.'
                ))

    @api.model
    def action_sync_master_relations(self):
        """Normalize existing flat master data during a module upgrade."""
        schedule_model = self.env[
            'rpc.hierarchy.logic.payment.schedule'
        ].with_context(active_test=False, skip_hierarchy_chain_check=True)
        logic_records = self.with_context(active_test=False).search(
            [], order='sequence, id'
        )

        for logic in logic_records:
            if logic.cost_group_code_id.hierarchy_id != logic.hierarchy_id:
                logic.cost_group_code_id.with_context(
                    skip_hierarchy_chain_check=True
                ).hierarchy_id = logic.hierarchy_id

            if (
                logic.cost_group_name_id.cost_group_code_id
                != logic.cost_group_code_id
            ):
                logic.cost_group_name_id.with_context(
                    skip_hierarchy_chain_check=True
                ).cost_group_code_id = logic.cost_group_code_id

            current_schedule = schedule_model.browse(
                logic.payment_schedule_id.id
            )
            target_schedule = schedule_model.search([
                ('cost_group_name_id', '=', logic.cost_group_name_id.id),
                ('name', '=', current_schedule.name),
            ], limit=1)
            if not target_schedule and not current_schedule.cost_group_name_id:
                current_schedule.cost_group_name_id = logic.cost_group_name_id
                target_schedule = current_schedule
            if not target_schedule:
                target_schedule = schedule_model.create({
                    'name': current_schedule.name,
                    'cost_group_name_id': logic.cost_group_name_id.id,
                    'sequence': current_schedule.sequence,
                    'active': current_schedule.active,
                })
            if logic.payment_schedule_id != target_schedule:
                logic.payment_schedule_id = target_schedule

        return True
