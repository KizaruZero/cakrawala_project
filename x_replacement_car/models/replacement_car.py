from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class ReplacementCar(models.Model):
    _name = 'replacement.car'
    _description = 'Replacement Car'
    _rec_name = 'name'
    _order = 'id desc'

    name = fields.Char(
        string="Reference",
        default='/',
        readonly=True
    )

    company_id = fields.Many2one(
        'res.company',
        string="Company Client",
        required=True,
        default=lambda self: self.env.company
    )

    vehicle_old_id = fields.Many2one(
        'fleet.vehicle',
        string="Broken Vehicle",
        required=True
    )

    vehicle_new_id = fields.Many2one(
        'fleet.vehicle',
        string="Replacement Vehicle"
    )
    
    spk_ids = fields.Many2many(
        'fleet.spk',
        string="SPK Reference",
        readonly=True
    )

    service_planning_id = fields.Many2one(
        'service.planning',
        string="Service Planning",
        ondelete='set null',
    )
    
    request_date = fields.Date(
        string="Request Date",
        default=fields.Date.today,
        required=True
    )
    
    pic_name = fields.Char(
        string="PIC Name",
        required=True
    )
    
    estimation_use_date = fields.Date(
        string="Estimation Use Date",
        required=True
    )

    reason = fields.Text(
        string="Reason"
    )


    
    old_license_plate = fields.Char(related='vehicle_old_id.fleet_document_license_plate', string="Old License Plate")
    old_vehicle_model_id = fields.Many2one('fleet.vehicle.model', related='vehicle_old_id.model_id', string="Old Vehicle Model")
    old_year = fields.Selection(related='vehicle_old_id.model_year', string="Old Year")
    old_color = fields.Char(related='vehicle_old_id.color', string="Old Color")

    new_company_client_id = fields.Many2one('res.company', related='vehicle_new_id.company_id', string="New Company Client")
    new_license_plate = fields.Char(related='vehicle_new_id.fleet_document_license_plate', string="New License Plate")
    new_vehicle_model_id = fields.Many2one('fleet.vehicle.model', related='vehicle_new_id.model_id', string="New Vehicle Model")
    new_year = fields.Selection(related='vehicle_new_id.model_year', string="New Year")
    new_color = fields.Char(related='vehicle_new_id.color', string="New Color")

    
    approval_line_ids = fields.One2many(
        'replacement.approval',
        'replacement_car_id',
        string="Approval Lines"
    )
    


    state = fields.Selection([
        ('draft', 'Draft'),
        ('waiting', 'Waiting Approval'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ], default='draft', tracking=True)

    can_approve = fields.Boolean(
        string="Current user can act",
        compute="_compute_can_approve",
    )

    @api.depends(
        "state",
        "approval_line_ids.state",
        "approval_line_ids.approver_id",
        "approval_line_ids.sequence",
    )
    def _compute_can_approve(self):
        user = self.env.user
        for rec in self:
            pending = rec.approval_line_ids.filtered(
                lambda l: l.state == "waiting"
            ).sorted("sequence")
            first = pending[:1]
            rec.can_approve = (
                rec.state == "waiting"
                and bool(first)
                and first.approver_id == user
            )

    def _get_next_waiting_approval_line(self):
        self.ensure_one()
        pending = self.approval_line_ids.filtered(
            lambda l: l.state == "waiting"
        ).sorted("sequence")
        return pending[:1]

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', '/') == '/':
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'replacement.car'
                ) or '/'
        return super().create(vals_list)

    @api.constrains('vehicle_old_id', 'vehicle_new_id')
    def _check_vehicle(self):
        for rec in self:
            if rec.vehicle_old_id and rec.vehicle_new_id:
                if rec.vehicle_old_id.id == rec.vehicle_new_id.id:
                    raise ValidationError(
                        "Replacement vehicle cannot be same as broken vehicle."
                    )
                
    def action_submit(self):
        for rec in self:
            rec._generate_approval_from_master()
            rec.state = 'waiting'

    def _generate_approval_from_master(self):
        """Copy master.approval (template) into replacement.approval for this document."""
        self.ensure_one()
        ApprovalLine = self.env['replacement.approval']
        ApprovalLine.search([('replacement_car_id', '=', self.id)]).unlink()
        templates = self.env['master.approval'].search([], order='sequence, id')
        if not templates:
            raise ValidationError(
                "Belum ada master approval. "
                "Isi daftar approver di menu Master Approval Replacement."
            )
        for tmpl in templates:
            if not tmpl.approver_id:
                raise ValidationError(
                    "Baris master approval urutan %s belum punya approver."
                    % (tmpl.sequence or tmpl.id)
                )
            ApprovalLine.create({
                'replacement_car_id': self.id,
                'sequence': tmpl.sequence,
                'approver_id': tmpl.approver_id.id,
                'state': 'waiting',
            })

    def action_approve(self):
        for rec in self:
            line = rec._get_next_waiting_approval_line()
            if not line:
                raise ValidationError(_("There is no approval step waiting."))
            if line.approver_id != self.env.user:
                raise ValidationError(_("Only the assigned approver can approve at this step."))
            line.write({
                "state": "approved",
                "approval_date": fields.Datetime.now(),
            })
            still_waiting = rec.approval_line_ids.filtered(lambda l: l.state == "waiting")
            rec.state = "waiting" if still_waiting else "approved"

    def action_reject(self):
        for rec in self:
            line = rec._get_next_waiting_approval_line()
            if not line:
                raise ValidationError(_("There is no approval step waiting."))
            if line.approver_id != self.env.user:
                raise ValidationError(_("Only the assigned approver can reject at this step."))
            line.write({
                "state": "rejected",
                "reject_date": fields.Datetime.now(),
            })
            rec.state = "rejected"
    
    def action_reset_to_draft(self):
        for rec in self:
            rec.ensure_one()
            rec.state = 'draft'
            rec.approval_line_ids.unlink()
            