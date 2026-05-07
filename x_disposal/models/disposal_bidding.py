from odoo import models, fields, api
from odoo.exceptions import ValidationError


class DisposalBidding(models.Model):
    _name = "disposal.bidding"
    _description = "Disposal Bidding"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "id desc"

    name = fields.Char(string="BID Number", required=True, copy=False, readonly=True, default="/")
    vehicle_id = fields.Many2one(
        "fleet.vehicle",
        string="Vehicle",
        required=True,
        ondelete="restrict",
        # Fleet uses state_id (Many2one to fleet.vehicle.state), not a plain "state" field.
        domain="[('state_id.name', '=', 'DISPOSAL')]",
    )
    asset_number = fields.Char(
        string="Asset Number",
        related="vehicle_id.asset_number",
        store=True,
        readonly=True,
    )
    license_plate = fields.Char(
        string="License Plate",
        related="vehicle_id.license_plate",
        store=True,
        readonly=True,
    )
    currency_id = fields.Many2one("res.currency", string="Currency", default=lambda self: self.env.company.currency_id)
    start_date = fields.Date(string="Start Date")
    end_date = fields.Date(string="End Date")
    open_price = fields.Monetary(string="Open Price", currency_field="currency_id")
    sales_price = fields.Monetary(string="Sales Price", currency_field="currency_id", compute="_compute_sales_price", store=True)
    potential_winner = fields.Char(string="Potential Winner", compute="_compute_potential_winner", store=True)
    state = fields.Selection([
        ("draft", "Draft"),
        ("waiting_approval", "Waiting Approval"),
        ("approved", "Approved"),
        ("rejected", "Rejected"),
    ], string="State", default="draft", tracking=True)
    is_editable = fields.Boolean(string='Is Editable', compute='_compute_is_editable')
    category = fields.Selection([
        ("internal", "Internal"),
        ("external", "External"),
    ], string="Category", required=True, default="external")

    bidding_line_ids = fields.One2many("disposal.bidding.line", "bidding_id", string="Bidding Lines")

    approval_tracking_ids = fields.One2many('disposal.approval.tracking', 'bidding_id', string='Approval Tracking')
    next_approver_id = fields.Many2one('res.users', string='Current Approver', compute='_compute_next_approver', store=True)
    can_current_user_approve = fields.Boolean(string='Can Current User Approve', compute='_compute_current_user_approval')
    can_current_user_delegate = fields.Boolean(string='Can Current User Delegate', compute='_compute_current_user_approval')
    current_user_approval_id = fields.Many2one('disposal.approval.tracking', string='Current User Approval', compute='_compute_current_user_approval')
    current_pending_approval_id = fields.Many2one('disposal.approval.tracking', string='Current Pending Approval', compute='_compute_current_user_approval')

    @api.depends('bidding_line_ids.bidding_price')
    def _compute_sales_price(self):
        for rec in self:
            if rec.bidding_line_ids:
                rec.sales_price = max(rec.bidding_line_ids.mapped('bidding_price') or [0])
            else:
                rec.sales_price = 0

    @api.depends('bidding_line_ids.bidding_price', 'bidding_line_ids.partner_id')
    def _compute_potential_winner(self):
        for rec in self:
            if rec.bidding_line_ids:
                highest_bid_line = max(rec.bidding_line_ids, key=lambda l: l.bidding_price or 0, default=None)
                rec.potential_winner = highest_bid_line.partner_id.display_name if highest_bid_line else ""
            else:
                rec.potential_winner = ""

    @api.depends('approval_tracking_ids.state')
    def _compute_next_approver(self):
        for rec in self:
            pending = rec.approval_tracking_ids.filtered(lambda t: t.state == 'pending').sorted(key=lambda r: (r.sequence, r.id))
            rec.next_approver_id = pending[:1].approver_id if pending else False

    @api.depends('approval_tracking_ids.state', 'approval_tracking_ids.approver_id', 'approval_tracking_ids.delegate_id', 'state')
    def _compute_current_user_approval(self):
        current_user = self.env.user
        is_admin = current_user.has_group('base.group_system')
        today = fields.Date.context_today(self)

        for request in self:
            next_pending = request.approval_tracking_ids.filtered(lambda t: t.state == 'pending').sorted(key=lambda t: (t.sequence, t.id))[:1]

            request.current_pending_approval_id = next_pending or False

            is_approver = next_pending and next_pending.approver_id == current_user
            is_valid_delegate = (next_pending and next_pending.delegate_id == current_user and next_pending._is_delegate_valid(today))

            if request.state == 'waiting_approval' and (is_approver or is_valid_delegate):
                request.can_current_user_approve = True
                request.current_user_approval_id = next_pending
            else:
                request.can_current_user_approve = False
                request.current_user_approval_id = False

            request.can_current_user_delegate = bool(
                request.state == 'waiting_approval' and next_pending and (next_pending.approver_id == current_user or is_admin)
            )

    @api.model_create_multi
    def create(self, vals_list):
        today = fields.Date.context_today(self)
        Seq = self.env['ir.sequence'].with_company(self.env.company)
        for vals in vals_list:
            if not vals.get('name') or vals.get('name') == '/':
                vals['name'] = Seq.next_by_code('disposal.bidding', sequence_date=today)
                if not vals['name']:
                    raise ValidationError(
                        'Sequence dengan kode "disposal.bidding" tidak ditemukan untuk perusahaan ini. '
                        'Buat atau perbaiki di Pengaturan → Teknis → Sequences.'
                    )
        return super().create(vals_list)

    def _post_approval_actions(self):
        # Placeholder for post-approval actions: e.g., create sale/purchase or notifications
        for rec in self:
            rec.message_post(body='Bidding approved. Post-approval hooks can be implemented.')

    def action_submit_for_approval(self):
        self._check_submission_requirements()
        for rec in self:
            rec._generate_approval_lines()
            rec.state = 'waiting_approval'
            rec._send_next_approver_notification(is_reminder=False)

    def _check_submission_requirements(self):
        for rec in self:
            if not rec.open_price:
                raise ValidationError('Open Price must be set before submit for approval.')

    def _generate_approval_lines(self):
        self.ensure_one()
        # Cancel old pending
        old_pending = self.approval_tracking_ids.filtered(lambda x: x.state == 'pending')
        if old_pending:
            old_pending.write({'state': 'cancelled', 'date': fields.Datetime.now()})

        # Find specific matrix (ignore category filter, use generic approval matrix)
        matrix = self.env['disposal.approval.matrix'].search([
            ('active', '=', True),
            ('is_default', '=', False),
        ], limit=1)

        if not matrix:
            matrix = self.env['disposal.approval.matrix'].search([
                ('active', '=', True), ('is_default', '=', True)
            ], limit=1)

        if not matrix:
            raise ValidationError('No approval matrix found. Please configure an approval matrix.')

        applicable = matrix.approval_line_ids.filtered(lambda l: l.active and l.starting_amount <= (self.open_price or 0)).sorted(key=lambda l: l.sequence)
        if not applicable:
            raise ValidationError('No approval line matched for this Bidding amount. Please review the approval matrix.')

        for line in applicable:
            approver = line.approver_id
            if not approver or not approver.active or approver.share:
                approver = self._get_default_approver_user()
            if not approver:
                raise ValidationError('No valid approver found. Please configure a valid approver.')

            self.env['disposal.approval.tracking'].create({
                'bidding_id': self.id,
                'sequence': line.sequence,
                'approver_id': approver.id,
                'delegate_id': line.delegate_id.id if line.delegate_id else False,
                'delegate_valid_from': line.delegate_valid_from or False,
                'delegate_valid_to': line.delegate_valid_to or False,
                'state': 'pending',
            })

    def _get_default_approver_user(self):
        current_user = self.env.user
        if current_user.active and not current_user.share and current_user.login != 'admin':
            return current_user
        return self.env['res.users'].search([('active', '=', True), ('share', '=', False), ('login', '!=', 'admin')], order='id asc', limit=1)

    def _send_next_approver_notification(self, is_reminder=False):
        for rec in self:
            if rec.state != 'waiting_approval' or not rec.next_approver_id:
                continue
            message = ('Reminder: %s is waiting your approval.' if is_reminder else '%s is waiting for your approval.') % rec.name
            rec.activity_schedule('mail.mail_activity_data_todo', user_id=rec.next_approver_id.id, summary='Bidding Approval', note=message)
            rec.message_post(body=message)

    def _open_approval_action_wizard(self, action_type):
        self.ensure_one()
        if not self.can_current_user_approve or not self.current_user_approval_id:
            raise ValidationError('You are not allowed to process this Bidding at the current approval stage.')
        return {
            'type': 'ir.actions.act_window',
            'name': 'Bidding Approval Action',
            'res_model': 'disposal.approval.action.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_bidding_id': self.id,
                'default_approval_tracking_id': self.current_user_approval_id.id,
                'default_action_type': action_type,
            }
        }

    def action_open_accept_wizard(self):
        self.ensure_one()
        return self._open_approval_action_wizard('approve')

    def action_open_reject_wizard(self):
        self.ensure_one()
        return self._open_approval_action_wizard('reject')

    def action_approve(self):
        for rec in self:
            if not rec.current_pending_approval_id:
                raise ValidationError('No pending approval stage found for this Bidding.')
            rec.current_pending_approval_id.action_approve()

    def action_reject(self):
        for rec in self:
            if not rec.current_pending_approval_id:
                raise ValidationError('No pending approval stage found for this Bidding.')
            rec.current_pending_approval_id.action_reject()
            
    def action_reset_to_draft(self):
        for rec in self:
            rec.state = 'draft'
            rec.approval_tracking_ids.with_context(allow_reset_to_draft=True).unlink()
            rec.message_post(body='Bidding reset to draft.')
            rec.bidding_line_ids.unlink()

    @api.depends('state')
    def _compute_is_editable(self):
        for rec in self:
            rec.is_editable = False if rec.state == 'approved' else True

    def write(self, vals):
        for rec in self:
            if rec.state == 'approved':
                raise ValidationError('Cannot modify a Bidding after it has been approved.')
        return super(DisposalBidding, self).write(vals)

    def unlink(self):
        for rec in self:
            if rec.state == 'approved':
                raise ValidationError('Cannot delete a Bidding after it has been approved.')
        return super(DisposalBidding, self).unlink()


class DisposalBiddingLine(models.Model):
    _name = "disposal.bidding.line"
    _description = "Disposal Bidding Line"

    bidding_id = fields.Many2one('disposal.bidding', string='Bidding', required=True, ondelete='cascade')
    sequence = fields.Integer(string='Sequence', default=10)
    partner_id = fields.Many2one(
        'res.partner',
        string='Showroom / Vendor',
        required=True,
        ondelete='restrict',
    )
    pic_name = fields.Char(string='PIC Name')
    bidding_price = fields.Float(string='Bidding Price', required=True)
    notes = fields.Text(string='Notes')
    attachment = fields.Binary(string='Attachment', attachment=True, required=True)
    attachment_filename = fields.Char(string='Attachment Filename')

    def write(self, vals):
        for rec in self:
            if rec.bidding_id and rec.bidding_id.state == 'approved':
                raise ValidationError('Cannot modify bidding lines after Bidding is approved.')
        return super(DisposalBiddingLine, self).write(vals)

    def unlink(self):
        for rec in self:
            if rec.bidding_id and rec.bidding_id.state == 'approved':
                raise ValidationError('Cannot delete bidding lines after Bidding is approved.')
        return super(DisposalBiddingLine, self).unlink()

    @api.model_create_multi
    def create(self, vals_list):
        # prevent creating lines for approved bidding
        for vals in vals_list:
            bidding_id = vals.get('bidding_id')
            if bidding_id:
                bidding = self.env['disposal.bidding'].browse(bidding_id)
                if bidding and bidding.state == 'approved':
                    raise ValidationError('Cannot add bidding lines after Bidding is approved.')
        return super(DisposalBiddingLine, self).create(vals_list)

