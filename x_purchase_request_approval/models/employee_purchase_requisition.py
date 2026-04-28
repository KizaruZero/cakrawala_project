# -*- coding: utf-8 -*-

from datetime import datetime
from odoo import api, fields, models, tools, _
from odoo.exceptions import ValidationError
from odoo.tools.misc import format_date
from odoo.tools import format_amount, format_list, formatLang, groupby

class PurchaseRequisition(models.Model):
    _inherit = 'employee.purchase.requisition'
    
    def write(self, vals):
        if self.requisition_order_ids:
            for line in self.requisition_order_ids:
                line.check_quantity()
        return super(PurchaseRequisition, self).write(vals)

    @api.depends('requisition_order_ids.total_price')
    def _compute_amount_total(self):
        for record in self:
            amount_total = 0
            for requisition_order_id in record.requisition_order_ids:
                amount_total += requisition_order_id.total_price
            record.amount_total = amount_total

    def _get_record_url(self):
        """URL langsung ke form PO ini di web client."""
        # base = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        # return f"{base}/web#id={self.id}&model=employee.purchase.requisition&view_type=form"
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        action = self.env.ref('employee_purchase_requisition.employee_purchase_requisition_action').id
        return f"{base_url}/odoo/action/action-{action}/{self.id}"

    def _send_next_approval_emails(self, user):
        """Kirim email notifikasi ke user approver berikutnya"""
        template = self.env.ref('x_purchase_request_approval.email_template_pr_next_approval')
        for record in self:
            pr_url = record._get_record_url()
            email = user.partner_id.email
            if not email:
                continue
            ctx = {
                'default_subject': f"[Approval Needed] PO {record.name}",
                'user_name': user.name,
                'pr_name': record.name or '',
                'requisition_date': format_date(record.env, record.requisition_date) if record.requisition_date else '',
                'vendor_name': record.partner_id.display_name or '',
                'pr_url': pr_url,
                'company_name': record.company_id.name or '',
            }
            template.with_context(ctx).send_mail(
                record.id,
                email_values={'email_to': email},
                force_send=True,
            )

    def _send_fully_approved_emails(self, user):
        template = self.env.ref('x_purchase_request_approval.email_template_pr_fully_approved')
        for record in self:
            pr_url = record._get_record_url()
            email = user.partner_id.email
            if not email:
                continue
            ctx = {
                'default_subject': f"[Fully Approved] PO {record.name}",
                'user_name': user.name,
                'po_name': record.name or '',
                'requisition_date': format_date(record.env, record.requisition_date) if record.requisition_date else '',
                'vendor_name': record.partner_id.display_name or '',
                'pr_url': pr_url,
                'company_name': record.company_id.name or '',
            }
            template.with_context(ctx).send_mail(
                record.id,
                email_values={'email_to': email},
                force_send=True,
            )

    def _send_rejected_emails(self, user):
        template = self.env.ref('x_purchase_request_approval.email_template_pr_rejected')
        for record in self:
            pr_url = record._get_record_url()
            email = user.partner_id.email
            if not email:
                continue
            ctx = {
                'default_subject': f"[Rejected] PR {record.name}",
                'user_name': user.name,
                'po_name': record.name or '',
                'requisition_date': format_date(record.env, record.requisition_date) if record.requisition_date else '',
                'vendor_name': record.partner_id.display_name or '',
                'pr_url': pr_url,
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
            purchase_requisition_approver_matrix_objs = self.env['purchase.requisition.approver.matrix'].search([
                ('employee_purchase_requisition_id', '=', record.id),
                ('actual_approver_id', '=', False)
            ], order='sequence')

            all_sequence = []
            first_approver_sequence = 0
            for purchase_requisition_approver_matrix_obj in purchase_requisition_approver_matrix_objs:
                all_sequence.append(int(purchase_requisition_approver_matrix_obj.sequence))
            all_sequence = list(set(all_sequence))
            if all_sequence:
                first_approver_sequence = all_sequence[0]

            next_purchase_request_approver_matrix_objs = self.env['purchase.requisition.approver.matrix'].search([
                ('employee_purchase_requisition_id', '=', record.id),
                ('sequence', '=', first_approver_sequence),
            ], order='sequence')

            record.current_approval_id = False
            for next_purchase_request_approver_matrix_obj in next_purchase_request_approver_matrix_objs:
                if next_purchase_request_approver_matrix_obj.approver_id:
                    record.current_approval_id = next_purchase_request_approver_matrix_obj.approver_id

    def _compute_next_approval_sequence(self):
        for record in self:
            purchase_requisition_approver_matrix_objs = self.env['purchase.requisition.approver.matrix'].search([
                ('employee_purchase_requisition_id', '=', record.id),
                ('actual_approver_id', '=', False)
            ], order='sequence')

            all_sequence = []
            first_approver_sequence = 0
            for purchase_requisition_approver_matrix_obj in purchase_requisition_approver_matrix_objs:
                all_sequence.append(int(purchase_requisition_approver_matrix_obj.sequence))
            all_sequence = list(set(all_sequence))
            if all_sequence:
                first_approver_sequence = all_sequence[0]
            record.next_approval_sequence = first_approver_sequence

            next_purchase_request_approver_matrix_objs = self.env['purchase.requisition.approver.matrix'].search([
                ('employee_purchase_requisition_id', '=', record.id),
                ('sequence', '=', first_approver_sequence),
            ], order='sequence')

            for next_purchase_request_approver_matrix_obj in next_purchase_request_approver_matrix_objs:
                if next_purchase_request_approver_matrix_obj.approver_id:
                    record._send_next_approval_emails(next_purchase_request_approver_matrix_obj.approver_id)
                if next_purchase_request_approver_matrix_obj.delegation_id:
                    record._send_next_approval_emails(next_purchase_request_approver_matrix_obj.delegation_id)

            record._compute_current_approval_id()

    def _default_partner_id(self):
        partner_ctx = self.env.context.get('default_partner_id')
        if partner_ctx:
            return partner_ctx

        domain = [('is_general_vendor', '=', True), ('active', '=', True)]
        domain += [('parent_id', '=', False)]
        return self.env['res.partner'].search(domain, order='name asc', limit=1)


    name = fields.Char(string="Reference No", readonly=True, copy=False)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('waiting_approval', 'Waiting Approval'),
        ('approved', 'Approved'),
        ('purchase_order_created', 'Purchase Order Created'),
        ('rejected', 'Rejected')
    ], default='draft', copy=False, tracking=True)
    dept_id = fields.Many2one(comodel_name='hr.department', string='Department', help='Select an department', required=False)
    user_id = fields.Many2one(comodel_name='res.users', related='employee_id.user_id', string='Responsible', required=False, help='User who is responsible for requisition')
    partner_id = fields.Many2one(comodel_name='res.partner', string='Vendor', help='Vendor for the requisition', default=lambda self: self._default_partner_id())
    # partner_id = fields.Many2one(comodel_name='res.partner', string='Vendor', help='Vendor for the requisition',
    #     domain="[('is_general_vendor', '=', True)]", default=lambda self: self._default_partner_id())
    purchase_request_type_id = fields.Many2one(comodel_name='purchase.request.type.master', string='PR Type', domain="[('state', '=', 'active')]", check_company=True)
    department_id = fields.Many2one("hr.department", string='Division', required=True)
    internal_reference = fields.Char(string='Internal Reference', required=True)
    description = fields.Char(string='Description')
    currency_id = fields.Many2one('res.currency', 'Currency', required=True, default=lambda self: self.env.company.currency_id.id)
    amount_total = fields.Monetary(string='Total', store=True, readonly=True, compute='_compute_amount_total')
    is_user_creator = fields.Boolean(compute='_compute_is_user_creator', copy=False)
    is_approver = fields.Boolean(compute='_compute_is_approver', copy=False)
    next_approval_sequence = fields.Integer(string='Next Approval Sequence', default=1, compute='_compute_next_approval_sequence', store=True)
    purchase_requisition_approver_matrix_ids = fields.One2many('purchase.requisition.approver.matrix', 'employee_purchase_requisition_id', 'Approver Matrix', copy=False)    
    is_po_has_approve = fields.Boolean(compute='_compute_is_po_has_approve', copy=False)


    @api.model_create_multi
    def create(self, vals_list):
        """Function to generate purchase requisition sequence"""
        for vals in vals_list:
            if not vals.get('company_id'):
                vals['company_id'] = self.env.company.id
            if vals.get('name', 'New') == 'New':
                company = self.env['res.company'].browse(vals['company_id'])
                company_code = company.company_code or company.code or str(company.id)
                vals['name'] = 'PR/' + company_code + '/' + self.env['ir.sequence'].with_company(company.id).next_by_code('employee.purchase.requisition') or 'New'
        result = super(PurchaseRequisition, self).create(vals_list)
        if result.requisition_order_ids:
            for line in result.requisition_order_ids:
                line.check_quantity()
        return result

    def button_submit_requisition(self):
        for line in self.requisition_order_ids:
            line._validate_distribution()
        today = fields.Date.context_today(self)
        for record in self:
            purchase_request_approval_config_master_objs = self.env['purchase.request.approval.config.master'].search([
                ('purchase_request_type_id', '=', record.purchase_request_type_id.id),
                ('department_id', '=', record.department_id.id),
                ('state', '=', 'active'),
                ('company_id', '=', record.company_id.id)
            ], order="sequence")

            if not purchase_request_approval_config_master_objs:
                raise ValidationError(_('No approval matrix found for this transaction. Please verify your data input or check the configuration.'))

            record.purchase_requisition_approver_matrix_ids.unlink()
            for purchase_request_approval_config_master_obj in purchase_request_approval_config_master_objs:
                if purchase_request_approval_config_master_obj.starting_amount <= record.amount_total:
                    in_window = (not purchase_request_approval_config_master_obj.date_valid_from or purchase_request_approval_config_master_obj.date_valid_from <= today) and \
                                (not purchase_request_approval_config_master_obj.date_valid_to   or today <= purchase_request_approval_config_master_obj.date_valid_to)

                    record.env['purchase.requisition.approver.matrix'].create({
                        'employee_purchase_requisition_id': record.id,
                        'sequence': purchase_request_approval_config_master_obj.sequence,
                        'approver_id': purchase_request_approval_config_master_obj.approver_id.id,
                        'delegation_id': purchase_request_approval_config_master_obj.delegation_id.id if (purchase_request_approval_config_master_obj.delegation_id and in_window) else False,
                        'state': 'waiting_approval',
                        'start_valid': purchase_request_approval_config_master_obj.date_valid_from,
                        'valid_until': purchase_request_approval_config_master_obj.date_valid_to,
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
            purchase_requisition_approver_matrix_objs = self.env['purchase.requisition.approver.matrix'].search([
                ('employee_purchase_requisition_id', '=', record.id),
                ('actual_approver_id', '=', False)
            ], order='sequence')

            all_sequence = []
            for purchase_requisition_approver_matrix_obj in purchase_requisition_approver_matrix_objs:
                all_sequence.append(int(purchase_requisition_approver_matrix_obj.sequence))
            all_sequence = list(set(all_sequence))

            user_allowed_to_approve_ids = []
            if all_sequence:
                first_approver_sequence = all_sequence[0]
                matrix_approver_objs = self.env['purchase.requisition.approver.matrix'].search([
                    ('employee_purchase_requisition_id', '=', record.id),
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

    def button_approve(self, notes=False):
        for record in self:
            purchase_requisition_approver_matrix_objs = self.env['purchase.requisition.approver.matrix'].search([
                ('employee_purchase_requisition_id', '=', record.id),
                ('actual_approver_id', '=', False)
            ], order='sequence')

            all_sequence = []
            for purchase_requisition_approver_matrix_obj in purchase_requisition_approver_matrix_objs:
                all_sequence.append(int(purchase_requisition_approver_matrix_obj.sequence))
            all_sequence = list(set(all_sequence))
            first_approver_sequence = all_sequence[0]

            if len(all_sequence) > 1:
                matrix_approver_objs = self.env['purchase.requisition.approver.matrix'].search([
                    ('employee_purchase_requisition_id', '=', record.id),
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
                next_matrix_approver_objs = self.env['purchase.requisition.approver.matrix'].search([
                    ('employee_purchase_requisition_id', '=', record.id),
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
                matrix_approver_objs = self.env['purchase.requisition.approver.matrix'].search([
                    ('employee_purchase_requisition_id', '=', record.id),
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
                    self.write({'state': 'approved', 'next_approval_sequence': 0})
                    for matrix_approver_obj in matrix_approver_objs:
                        matrix_approver_obj.write({
                            'actual_approver_id': self.env.user.id,
                            'state': 'approved',
                            'date_approved': fields.Datetime.now()
                        })
                    [line.add_remaining_qty() for line in record.requisition_order_ids]
                    record._send_fully_approved_emails(record.create_uid)
                else:
                    raise ValidationError(_('You do not have access to approve this document. Please ask ' + ', '.join(approvers) + ' to approve!'))

    def button_reject_wizard(self):
        ctx = self.env.context.copy()
        ctx.update({'default_employee_purchase_requisition_id': self.id})
        action = self.sudo().env["ir.actions.actions"]._for_xml_id("x_purchase_request_approval.action_pr_reject_reason_wizard")
        action['context'] = ctx
        return action
    
    def button_approve_wizard(self):
        ctx = self.env.context.copy()
        ctx.update({'default_employee_purchase_requisition_id': self.id})
        action = self.sudo().env["ir.actions.actions"]._for_xml_id("x_purchase_request_approval.action_pr_approve_wizard")
        action['context'] = ctx
        return action

    def button_reject(self, notes=False):
        for record in self:
            purchase_requisition_approver_matrix_objs = self.env['purchase.requisition.approver.matrix'].search([
                ('employee_purchase_requisition_id', '=', record.id),
                ('actual_approver_id', '=', False)
            ], order='sequence')

            all_sequence = []
            for purchase_requisition_approver_matrix_obj in purchase_requisition_approver_matrix_objs:
                all_sequence.append(int(purchase_requisition_approver_matrix_obj.sequence))
            all_sequence = list(set(all_sequence))
            first_approver_sequence = all_sequence[0]

            if len(all_sequence) > 1:
                matrix_approver_objs = self.env['purchase.requisition.approver.matrix'].search([
                    ('employee_purchase_requisition_id', '=', record.id),
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
                next_matrix_approver_objs = self.env['purchase.requisition.approver.matrix'].search([
                    ('employee_purchase_requisition_id', '=', record.id),
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
                matrix_approver_objs = self.env['purchase.requisition.approver.matrix'].search([
                    ('employee_purchase_requisition_id', '=', record.id),
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
                record.purchase_requisition_approver_matrix_ids.unlink()
                record.write({'state': 'draft'})
            else:
                raise ValidationError(_('You do not have access to revise this document. Please ask ' + ', '.join(approvers) + ' to approve!'))

    def button_create_purchase_order(self):
        """Create purchase order"""
        for record in self:
            order_line = []
            for requisition_order_id in record.requisition_order_ids:
                order_line.append((0, 0, {
                    'line_no': requisition_order_id.line_no,
                    'product_id': requisition_order_id.product_id.id,
                    'product_qty': requisition_order_id.quantity,
                    'price_unit': requisition_order_id.estimate_price,
                    'analytic_distribution': requisition_order_id.analytic_distribution,
                    'remark': requisition_order_id.remark,
                    'product_uom_id': requisition_order_id.uom_id.id,
                }))

            self.env['purchase.order'].create({
                'partner_id': record.partner_id.id,
                'requisition_order': record.name,
                'source_document': record.internal_reference,
                'order_line': order_line
            })
        self.write({'state': 'purchase_order_created'})

    def _compute_is_po_has_approve(self):
        for record in self:
            record.is_po_has_approve = False
            purchase_order_objs = self.env['purchase.order'].search_count([('requisition_order', '=', record.name), ('state', 'in', ['purchase','done'])])
            if purchase_order_objs:
                record.is_po_has_approve = True

    def update_uom(self):
        for rec in self:
            for line in rec.requisition_order_ids:
                line.uom_id = line.product_id.uom_id

class PurchaseRequisitionApproverMatrix(models.Model):
    _name = 'purchase.requisition.approver.matrix'
    _order = 'sequence'

    employee_purchase_requisition_id = fields.Many2one(comodel_name='employee.purchase.requisition', string='Purchase Requisition')
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