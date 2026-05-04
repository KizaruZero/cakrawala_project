from odoo import models, fields, api
from odoo.exceptions import ValidationError


class ReplacementCar(models.Model):
    _name = 'replacement.car'
    _description = 'Replacement Car'
    _rec_name = 'name'
    _order = 'id desc'

    # =========================================
    # BASIC
    # =========================================
    name = fields.Char(
        string="Reference",
        default='/',
        readonly=True
    )

    customer_id = fields.Many2one(
        'res.partner',
        string="Customer",
        required=True
    )

    request_date = fields.Date(
        string="Request Date",
        default=fields.Date.today,
        required=True
    )

    reason = fields.Text(
        string="Reason"
    )

    # =========================================
    # VEHICLE
    # =========================================
    vehicle_old_id = fields.Many2one(
        'fleet.vehicle',
        string="Broken Vehicle",
        required=True
    )

    service_planning_id = fields.Many2one(
        'service.planning',
        string="Service Planning",
        readonly=True
    )

    vehicle_new_id = fields.Many2one(
        'fleet.vehicle',
        string="Replacement Vehicle"
    )

    stock_available = fields.Boolean(
        string="Stock Available"
    )

    is_issued = fields.Boolean(
        string="Unit Issued", default=False
    )

    # =========================================
    # STATUS
    # =========================================
    state = fields.Selection([
        ('draft', 'Draft'),
        ('waiting', 'Waiting Approval'),
        ('approved', 'Approved'),
        ('done', 'Done'),
        ('cancel', 'Cancelled'),
    ], default='draft', tracking=True)

    note = fields.Text(string="Internal Note")

    # =========================================
    # AUTO NUMBER
    # =========================================
    @api.model
    def create(self, vals):
        if vals.get('name', '/') == '/':
            vals['name'] = self.env['ir.sequence'].next_by_code(
                'replacement.car'
            ) or '/'
        return super().create(vals)

    # =========================================
    # VALIDATION
    # =========================================
    @api.constrains('vehicle_old_id', 'vehicle_new_id')
    def _check_vehicle(self):
        for rec in self:
            if rec.vehicle_old_id and rec.vehicle_new_id:
                if rec.vehicle_old_id.id == rec.vehicle_new_id.id:
                    raise ValidationError(
                        "Replacement vehicle cannot be same as broken vehicle."
                    )
                
    @api.onchange('vehicle_new_id')
    def _onchange_vehicle_new(self):
        for rec in self:
            if rec.vehicle_new_id:
                rec.stock_available = True
            else:
                rec.stock_available = False

    def action_check_stock(self):
        for rec in self:
            if rec.vehicle_new_id:
                rec.stock_available = True
            else:
                rec.stock_available = False

    def action_issue_unit(self):
        for rec in self:
            if not rec.stock_available:
                raise ValidationError("Stock tidak tersedia!")

            rec.is_issued = True

    # =========================================
    # WORKFLOW
    # =========================================
    def action_submit(self):
        self.state = 'waiting'

    def action_approve(self):
        for rec in self:
            if not rec.stock_available:
                raise ValidationError("Unit replacement tidak tersedia!")
            
            if not rec.is_issued:
                raise ValidationError("Unit belum di-issue!")

            rec.state = 'approved'

            # assign kendaraan ke customer
            if rec.vehicle_new_id:
                rec.vehicle_new_id.write({
                    'driver_id': rec.customer_id.id
                })
            
            # nonaktifkan kendaraan lama
            if rec.vehicle_old_id:
                rec.vehicle_old_id.write({
                    'active': False
                })

    def action_done(self):
        self.state = 'done'

    def action_cancel(self):
        self.state = 'cancel'

    