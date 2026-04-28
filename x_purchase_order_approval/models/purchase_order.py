# -*- coding: utf-8 -*-

from datetime import datetime
from odoo import api, fields, models, tools, _
from odoo.exceptions import ValidationError
from odoo.tools.misc import format_date
from odoo.tools.float_utils import float_compare


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'
    

    def _get_record_url(self):
        """URL langsung ke form PO ini di web client."""
        # base = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        # return f"{base}/web#id={self.id}&model=purchase.order&view_type=form"
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        action = self.env.ref('purchase.purchase_rfq').id
        return f"{base_url}/odoo/action/action-{action}/{self.id}"

    def _send_next_approval_emails(self, user):
        """Kirim email notifikasi ke user approver berikutnya"""
        template = self.env.ref('x_purchase_order_approval.email_template_po_next_approval')
        for record in self:
            po_url = record._get_record_url()
            email = user.partner_id.email
            if not email:
                continue
            ctx = {
                'default_subject': f"[Approval Needed] PO {record.name}",
                'user_name': user.name,
                'po_name': record.name or '',
                'date_order': format_date(record.env, record.date_order) if record.date_order else '',
                'vendor_name': record.partner_id.display_name or '',
                'po_url': po_url,
                'company_name': record.company_id.name or '',
            }
            template.with_context(ctx).send_mail(
                record.id,
                email_values={'email_to': email},
                force_send=True,
            )

    def _send_fully_approved_emails(self, user):
        template = self.env.ref('x_purchase_order_approval.email_template_po_fully_approved')
        for record in self:
            po_url = record._get_record_url()
            email = user.partner_id.email
            if not email:
                continue
            ctx = {
                'default_subject': f"[Fully Approved] PO {record.name}",
                'user_name': user.name,
                'po_name': record.name or '',
                'date_order': format_date(record.env, record.date_order) if record.date_order else '',
                'vendor_name': record.partner_id.display_name or '',
                'po_url': po_url,
                'company_name': record.company_id.name or '',
            }
            template.with_context(ctx).send_mail(
                record.id,
                email_values={'email_to': email},
                force_send=True,
            )

    def _send_rejected_emails(self, user):
        template = self.env.ref('x_purchase_order_approval.email_template_po_rejected')
        for record in self:
            po_url = record._get_record_url()
            email = user.partner_id.email
            if not email:
                continue
            ctx = {
                'default_subject': f"[Rejected] PO {record.name}",
                'user_name': user.name,
                'po_name': record.name or '',
                'date_order': format_date(record.env, record.date_order) if record.date_order else '',
                'vendor_name': record.partner_id.display_name or '',
                'po_url': po_url,
                'company_name': record.company_id.name or '',
            }
            template.with_context(ctx).send_mail(
                record.id,
                email_values={'email_to': email},
                force_send=True,
            )
    current_approval_id = fields.Many2one(comodel_name='res.users', string='Current Approval', compute='_compute_current_approval_id', store=True)

    def _compute_current_approval_id(self):
        for record in self:
            purchase_order_approver_matrix_objs = self.env['purchase.order.approver.matrix'].search([
                ('purchase_order_id', '=', record.id),
                ('actual_approver_id', '=', False)
            ], order='sequence')

            all_sequence = []
            first_approver_sequence = 0
            for purchase_order_approver_matrix_obj in purchase_order_approver_matrix_objs:
                all_sequence.append(int(purchase_order_approver_matrix_obj.sequence))
            all_sequence = list(set(all_sequence))
            if all_sequence:
                first_approver_sequence = all_sequence[0]

            next_purchase_order_approver_matrix_objs = self.env['purchase.order.approver.matrix'].search([
                ('purchase_order_id', '=', record.id),
                ('sequence', '=', first_approver_sequence),
            ], order='sequence')

            record.current_approval_id = False
            for next_purchase_order_approver_matrix_obj in next_purchase_order_approver_matrix_objs:
                if next_purchase_order_approver_matrix_obj.approver_id:
                    record.current_approval_id = next_purchase_order_approver_matrix_obj.approver_id

    def _compute_next_approval_sequence(self):
        for record in self:
            purchase_order_approver_matrix_objs = self.env['purchase.order.approver.matrix'].search([
                ('purchase_order_id', '=', record.id),
                ('actual_approver_id', '=', False)
            ], order='sequence')

            all_sequence = []
            first_approver_sequence = 0
            for purchase_order_approver_matrix_obj in purchase_order_approver_matrix_objs:
                all_sequence.append(int(purchase_order_approver_matrix_obj.sequence))
            all_sequence = list(set(all_sequence))
            if all_sequence:
                first_approver_sequence = all_sequence[0]
            record.next_approval_sequence = first_approver_sequence

            next_purchase_order_approver_matrix_objs = self.env['purchase.order.approver.matrix'].search([
                ('purchase_order_id', '=', record.id),
                ('sequence', '=', first_approver_sequence),
            ], order='sequence')

            for next_purchase_order_approver_matrix_obj in next_purchase_order_approver_matrix_objs:
                if next_purchase_order_approver_matrix_obj.approver_id:
                    record._send_next_approval_emails(next_purchase_order_approver_matrix_obj.approver_id)
                if next_purchase_order_approver_matrix_obj.delegation_id:
                    record._send_next_approval_emails(next_purchase_order_approver_matrix_obj.delegation_id)

            record._compute_current_approval_id()


    state = fields.Selection([
        ('draft', 'RFQ'),
        ('waiting_approval', 'Waiting Approval'),
        ('sent', 'RFQ Sent'),
        ('to approve', 'To Approve'),
        ('purchase', 'Purchase Order'),
        ('done', 'Locked'),
        ('cancel', 'Cancelled'),
        ('rejected', 'Rejected')
    ], string='Status', readonly=True, index=True, copy=False, default='draft', tracking=True)
    quotation_date = fields.Date('Quotation Date', index=True, copy=False, default=fields.Date.today)
    supply_service_date = fields.Char('Supply / Service Date', copy=False, default='Immediate Once Ready')
    supply_service_port = fields.Char('Supply / Service Port', copy=False, default='See Delivery Instruction')
    purchase_order_vesel_master_id = fields.Many2one(comodel_name='purchase.order.vesel.master', string='Vesel', check_company=True)
    purchase_order_type_master_id = fields.Many2one(comodel_name='purchase.order.type.master', string='PO Type', check_company=True)
    department_id = fields.Many2one("hr.department", string='Division')
    source_document = fields.Char(string='Source Document')
    purchase_order_approver_matrix_ids = fields.One2many('purchase.order.approver.matrix', 'purchase_order_id', 'Approver Matrix', copy=False)
    next_approval_sequence = fields.Integer(string='Next Approval Sequence', default=1, compute='_compute_next_approval_sequence', store=True)
    is_user_creator = fields.Boolean(compute='_compute_is_user_creator', copy=False)
    is_approver = fields.Boolean(compute='_compute_is_approver', copy=False)

    purchase_assign_id = fields.Many2one(comodel_name='hr.employee', string='Purchase Assign')
    company_report_id = fields.Many2one(comodel_name='res.company', string='Company Report')
    in_charge = fields.Char('In Charge', copy=False)
    delivery_instruction = fields.Html(string='Delivery Instruction')
    important_notes = fields.Html(string='Important Notes')
    reject_reason = fields.Text('Reject Reason', copy=False)


    def button_submit_purchase_order(self):
        today = fields.Date.context_today(self)
        for record in self:
            if not record.purchase_order_type_master_id:
                raise ValidationError(_('PO Type is mandatory field.'))

            if not record.department_id:
                raise ValidationError(_('Division is mandatory field.'))

            purchase_order_approval_config_master_objs = self.env['purchase.order.approval.config.master'].search([
                ('purchase_order_type_id', '=', record.purchase_order_type_master_id.id),
                ('department_id', '=', record.department_id.id),
                ('state', '=', 'active'),
                ('company_id', '=', record.company_id.id)
            ], order="sequence")

            if not purchase_order_approval_config_master_objs:
                raise ValidationError(_('No approval matrix found for this transaction. Please verify your data input or check the configuration.'))

            date_rate = record.date_order or today ### tanggal kurs yang dipakai
            record.purchase_order_approver_matrix_ids.unlink()
            for purchase_order_approval_config_master_obj in purchase_order_approval_config_master_objs:
                cmp_cur = purchase_order_approval_config_master_obj.currency_id or record.company_id.currency_id
                po_total_in_cfg_cur = record.currency_id._convert(record.amount_total, cmp_cur, record.company_id, date_rate)
                # if purchase_order_approval_config_master_obj.starting_amount <= record.amount_total:
                if float_compare(po_total_in_cfg_cur, purchase_order_approval_config_master_obj.starting_amount, precision_rounding=cmp_cur.rounding) >= 0:
                    in_window = (not purchase_order_approval_config_master_obj.date_valid_from or purchase_order_approval_config_master_obj.date_valid_from <= today) and \
                                (not purchase_order_approval_config_master_obj.date_valid_to   or today <= purchase_order_approval_config_master_obj.date_valid_to)
                    record.env['purchase.order.approver.matrix'].create({
                        'purchase_order_id': record.id,
                        'sequence': purchase_order_approval_config_master_obj.sequence,
                        'approver_id': purchase_order_approval_config_master_obj.approver_id.id,
                        'delegation_id': purchase_order_approval_config_master_obj.delegation_id.id if (purchase_order_approval_config_master_obj.delegation_id and in_window) else False,
                        'state': 'waiting_approval',
                        'start_valid': purchase_order_approval_config_master_obj.date_valid_from,
                        'valid_until': purchase_order_approval_config_master_obj.date_valid_to,
                    })
            record.write({'state': 'waiting_approval'})
            record._compute_next_approval_sequence()

    def _compute_is_user_creator(self):
        for record in self:
            record.is_user_creator = False
            if self.env.user.id == record.create_uid.id:
                record.is_user_creator = True

    def _compute_is_approver(self):
        for record in self:
            purchase_order_approver_matrix_objs = self.env['purchase.order.approver.matrix'].search([
                ('purchase_order_id', '=', record.id),
                ('actual_approver_id', '=', False)
            ], order='sequence')

            all_sequence = []
            for purchase_order_approver_matrix_obj in purchase_order_approver_matrix_objs:
                all_sequence.append(int(purchase_order_approver_matrix_obj.sequence))
            all_sequence = list(set(all_sequence))

            user_allowed_to_approve_ids = []
            if all_sequence:
                first_approver_sequence = all_sequence[0]
                matrix_approver_objs = self.env['purchase.order.approver.matrix'].search([
                    ('purchase_order_id', '=', record.id),
                    ('sequence', '=', first_approver_sequence),
                    ('actual_approver_id', '=', False)
                ], order='sequence')

                for matrix_approver_obj in matrix_approver_objs:
                    user_allowed_to_approve_ids.append(matrix_approver_obj.approver_id.id)

                    ### for delegation_id
                    if matrix_approver_obj.delegation_id:
                        user_allowed_to_approve_ids.append(matrix_approver_obj.delegation_id.id)

            record.is_approver = False
            if self.env.user.id in user_allowed_to_approve_ids:
                record.is_approver = True

    def button_approve_purchase(self, notes=False):
        for record in self:
            purchase_order_approver_matrix_objs = self.env['purchase.order.approver.matrix'].search([
                ('purchase_order_id', '=', record.id),
                ('actual_approver_id', '=', False)
            ], order='sequence')

            all_sequence = []
            for purchase_order_approver_matrix_obj in purchase_order_approver_matrix_objs:
                all_sequence.append(int(purchase_order_approver_matrix_obj.sequence))
            all_sequence = list(set(all_sequence))
            first_approver_sequence = all_sequence[0]

            if len(all_sequence) > 1:
                matrix_approver_objs = self.env['purchase.order.approver.matrix'].search([
                    ('purchase_order_id', '=', record.id),
                    ('sequence', '=', first_approver_sequence),
                    ('actual_approver_id', '=', False)
                ], order='sequence')

                approvers = []
                user_allowed_to_approve_ids = []
                for matrix_approver_obj in matrix_approver_objs:
                    approvers.append(matrix_approver_obj.approver_id.name)
                    user_allowed_to_approve_ids.append(matrix_approver_obj.approver_id.id)

                    ### for delegation_id
                    if matrix_approver_obj.delegation_id:
                        approvers.append(matrix_approver_obj.delegation_id.name)
                        user_allowed_to_approve_ids.append(matrix_approver_obj.delegation_id.id)

                # Get next approver
                next_approver_sequence = all_sequence[1]
                next_matrix_approver_objs = self.env['purchase.order.approver.matrix'].search([
                    ('purchase_order_id', '=', record.id),
                    ('sequence', '=', next_approver_sequence),
                    ('actual_approver_id', '=', False)
                ], order='sequence')

                if self.env.user.id in user_allowed_to_approve_ids:
                    for matrix_approver_obj in matrix_approver_objs:
                        matrix_approver_obj.write({
                            'actual_approver_id': self.env.user.id,
                            'state': 'approved',
                            'date_approved': fields.Datetime.now()
                        })
                    record._compute_next_approval_sequence()
                else:
                    raise ValidationError(_('You do not have access to approve this document. Please ask ' + ', '.join(approvers) + ' to approve!'))
            else:
                matrix_approver_objs = self.env['purchase.order.approver.matrix'].search([
                    ('purchase_order_id', '=', record.id),
                    ('sequence', '=', first_approver_sequence),
                    ('actual_approver_id', '=', False)
                ], order='sequence')

                approvers = []
                user_allowed_to_approve_ids = []
                for matrix_approver_obj in matrix_approver_objs:
                    approvers.append(matrix_approver_obj.approver_id.name)
                    user_allowed_to_approve_ids.append(matrix_approver_obj.approver_id.id)

                    ### for delegation_id
                    if matrix_approver_obj.delegation_id:
                        approvers.append(matrix_approver_obj.delegation_id.name)
                        user_allowed_to_approve_ids.append(matrix_approver_obj.delegation_id.id)

                if self.env.user.id in user_allowed_to_approve_ids:
                    record.write({'next_approval_sequence': 0})
                    record.button_approve()
                    for matrix_approver_obj in matrix_approver_objs:
                        matrix_approver_obj.write({
                            'actual_approver_id': self.env.user.id,
                            'state': 'approved',
                            'date_approved': fields.Datetime.now()
                        })
                    record._send_fully_approved_emails(record.create_uid)
                else:
                    raise ValidationError(_('You do not have access to approve this document. Please ask ' + ', '.join(approvers) + ' to approve!'))

    def button_reject_wizard(self):
        ctx = self.env.context.copy()
        ctx.update({'default_purchase_order_id': self.id})
        action = self.sudo().env["ir.actions.actions"]._for_xml_id("x_purchase_order_approval.action_po_reject_reason_wizard")
        action['context'] = ctx
        return action

    def button_reject(self, notes=False):
        for record in self:
            purchase_order_approver_matrix_objs = self.env['purchase.order.approver.matrix'].search([
                ('purchase_order_id', '=', record.id),
                ('actual_approver_id', '=', False)
            ], order='sequence')

            all_sequence = []
            for purchase_order_approver_matrix_obj in purchase_order_approver_matrix_objs:
                all_sequence.append(int(purchase_order_approver_matrix_obj.sequence))
            all_sequence = list(set(all_sequence))
            first_approver_sequence = all_sequence[0]

            if len(all_sequence) > 1:
                matrix_approver_objs = self.env['purchase.order.approver.matrix'].search([
                    ('purchase_order_id', '=', record.id),
                    ('sequence', '=', first_approver_sequence),
                    ('actual_approver_id', '=', False)
                ], order='sequence')

                approvers = []
                user_allowed_to_approve_ids = []
                for matrix_approver_obj in matrix_approver_objs:
                    approvers.append(matrix_approver_obj.approver_id.name)
                    user_allowed_to_approve_ids.append(matrix_approver_obj.approver_id.id)

                    ### for delegation_id
                    if matrix_approver_obj.delegation_id:
                        approvers.append(matrix_approver_obj.delegation_id.name)
                        user_allowed_to_approve_ids.append(matrix_approver_obj.delegation_id.id)

                # Get next approver
                next_approver_sequence = all_sequence[1]
                next_matrix_approver_objs = self.env['purchase.order.approver.matrix'].search([
                    ('purchase_order_id', '=', record.id),
                    ('sequence', '=', next_approver_sequence),
                    ('actual_approver_id', '=', False)
                ], order='sequence')

                if self.env.user.id in user_allowed_to_approve_ids:
                    record.write({'state': 'rejected', 'next_approval_sequence': 0})
                    for matrix_approver_obj in matrix_approver_objs:
                        matrix_approver_obj.write({
                            'reject_by_id': self.env.user.id,
                            'state': 'rejected',
                            'date_rejected': fields.Datetime.now()
                        })
                    record._send_rejected_emails(record.create_uid)
                else:
                    raise ValidationError(_('You do not have access to approve this document. Please ask ' + ', '.join(approvers) + ' to approve!'))
            else:
                matrix_approver_objs = self.env['purchase.order.approver.matrix'].search([
                    ('purchase_order_id', '=', record.id),
                    ('sequence', '=', first_approver_sequence),
                    ('actual_approver_id', '=', False)
                ], order='sequence')

                approvers = []
                user_allowed_to_approve_ids = []
                for matrix_approver_obj in matrix_approver_objs:
                    approvers.append(matrix_approver_obj.approver_id.name)
                    user_allowed_to_approve_ids.append(matrix_approver_obj.approver_id.id)

                    ### for delegation_id
                    if matrix_approver_obj.delegation_id:
                        approvers.append(matrix_approver_obj.delegation_id.name)
                        user_allowed_to_approve_ids.append(matrix_approver_obj.delegation_id.id)

                if self.env.user.id in user_allowed_to_approve_ids:
                    record.write({'state': 'rejected', 'next_approval_sequence': 0})
                    for matrix_approver_obj in matrix_approver_objs:
                        matrix_approver_obj.write({
                            'reject_by_id': self.env.user.id,
                            'state': 'rejected',
                            'date_rejected': fields.Datetime.now()
                        })
                    record._send_rejected_emails(record.create_uid)
                else:
                    raise ValidationError(_('You do not have access to approve this document. Please ask ' + ', '.join(approvers) + ' to approve!'))

    def button_revise(self, notes=False):
        for record in self:
            if self.env.user.id == record.create_uid.id:
                record.purchase_order_approver_matrix_ids.unlink()
                record.write({'state': 'draft'})
            else:
                raise ValidationError(_('You do not have access to revise this document. Please ask ' + ', '.join(approvers) + ' to approve!'))
            
    def update_lines_name(self):
        for record in self:
            for line in record.order_line:
                line._compute_price_unit_and_date_planned_and_name()
                if line.requisition_line_id and line.requisition_line_id.product_id and line.requisition_line_id.description:
                    line.name = line.product_id.name + '\n' + line.description


class PurchaseOrderApproverMatrix(models.Model):
    _name = 'purchase.order.approver.matrix'
    _order = 'sequence'

    purchase_order_id = fields.Many2one(comodel_name='purchase.order', string='Purchase Order')
    sequence = fields.Integer(string='Sequence', default=1)
    approver_id = fields.Many2one(comodel_name='res.users', string='Approver')
    delegation_id = fields.Many2one(comodel_name='res.users', string='Delegation')
    actual_approver_id = fields.Many2one(comodel_name='res.users', string='Actual')
    reject_by_id = fields.Many2one(comodel_name='res.users', string='Rejected By')
    state = fields.Selection([
        ('waiting_approval', 'Waiting Approval'),
        ('approved', 'Approved'),
        ('rejected','Rejected'),
    ], string="Status", required=True, default='waiting_approval')
    date_approved = fields.Datetime('Date Approved')
    date_rejected = fields.Datetime('Date Rejected')
    start_valid = fields.Date('Start Valid')
    valid_until = fields.Date('Valid Until')
    # start_date_approved = fields.Date('Start Date Approved')
    # reminder_date = fields.Date('Reminder Date')
    # date_approved_string = fields.Char('Date Approved String', compute="_compute_date_string", store=True)
    # reminder_once_in = fields.Integer(string='Reminder Once In (Day)', default=1)