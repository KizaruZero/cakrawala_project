from odoo import models, fields, api
from odoo.exceptions import ValidationError

class ServicePlanning(models.Model):
    _name = 'service.planning'
    _description = 'Service Planning'
    _rec_name = 'name'
    _order = 'id desc'

    name = fields.Char(string="Name", readonly=True, default='/')
    vehicle_id = fields.Many2one('fleet.vehicle', string="Vehicle", required=True)
    need_replacement = fields.Boolean(string="Need Replacement Car")
    sequence = fields.Integer(string="Sequence", default=10)

    license_plate = fields.Char(
        related='vehicle_id.fleet_document_license_plate',
        string='License Plate',
        store=True,
        readonly=True,
    )
    vin_number = fields.Char(
        related='vehicle_id.fleet_document_vin_number',
        string='VIN Number',
        store=True,
        readonly=True,
    )
    engine_number = fields.Char(
        related='vehicle_id.engine_number',
        string='Engine Number',
        store=True,
        readonly=True,
    )
    asset_number = fields.Char(
        related='vehicle_id.fleet_document_asset_number',
        string='Asset Number',
        store=True,
        readonly=True,
    )
    model_year = fields.Selection(
        related='vehicle_id.model_year',
        string='Year',
        store=True,
        readonly=True,
    )

    line_ids = fields.One2many('service.planning.line', 'planning_id', string="Service Parts")

    @api.model_create_multi
    def create(self, vals_list):        
        for vals in vals_list:
            if vals.get('vehicle_id') and not vals.get('name'):
                vehicle = self.env['fleet.vehicle'].browse(vals['vehicle_id'])
                vals['name'] = f"Service Planning - {vehicle.name}"
        return super().create(vals_list)

    @api.onchange('vehicle_id')
    def _onchange_vehicle(self):
        for rec in self:
            if rec.vehicle_id:
                rec.name = f"Service Planning - {rec.vehicle_id.name}"
            else:
                rec.name = '/'

    def action_create_spk(self):
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Info',
                'message': 'SPK akan dibuat di tahap integrasi',
                'type': 'success',
            }
        }
    
    def action_create_replacement(self):
        self.ensure_one()
        vehicle = self.vehicle_id
        company = vehicle.company_id or self.env.company
        pic = vehicle.driver_id.name if vehicle.driver_id else '/'

        existing = self.env['replacement.car'].search([
            ('service_planning_id', '=', self.id),
            ('state', '!=', 'cancel'),
        ], limit=1)

        if existing:
            return {
                'type': 'ir.actions.act_window',
                'name': 'Replacement Car',
                'res_model': 'replacement.car',
                'view_mode': 'form',
                'res_id': existing.id,
                'target': 'current',
            }

        replacement = self.env['replacement.car'].create({
            'company_id': company.id,
            'vehicle_old_id': vehicle.id,
            'service_planning_id': self.id,
            'request_date': fields.Date.context_today(self),
            'pic_name': pic,
            'estimation_use_date': fields.Date.context_today(self),
            'reason': '',
        })

        return {
            'type': 'ir.actions.act_window',
            'name': 'Replacement Car',
            'res_model': 'replacement.car',
            'view_mode': 'form',
            'res_id': replacement.id,
            'target': 'current',
        }

class ServicePlanningLine(models.Model):
    _name = 'service.planning.line'
    _description = 'Service Planning Line'
    _order = 'sequence, id'

    planning_id = fields.Many2one('service.planning', string="Service Planning", required=True, ondelete='cascade')
    sequence = fields.Integer(string="Sequence", default=10)

    service_part = fields.Many2one(
        'product.template',
        string="Service Part",
        domain="[('type','=','service')]",
        required=True
    )
    kilometer = fields.Char(string="Kilometer", required=True)
    interval = fields.Integer(string="Interval (Month)", required=True)
    brand_recommendation = fields.Char()
    remarks = fields.Text()

    @api.constrains('kilometer', 'interval')
    def _check_values(self):
        for rec in self:
            try:
                km_value = int(rec.kilometer or 0)
            except (TypeError, ValueError):
                raise ValidationError("Kilometer harus berupa angka bulat")
            if km_value <= 0:
                raise ValidationError("Kilometer harus lebih dari 0")
            if rec.interval <= 0:
                raise ValidationError("Interval harus lebih dari 0")

    @api.constrains('planning_id', 'service_part', 'kilometer')
    def _check_unique_line(self):
        for rec in self:
            existing = self.search([
                ('planning_id', '=', rec.planning_id.id),
                ('service_part', '=', rec.service_part.id),
                ('kilometer', '=', str(rec.kilometer)),
                ('id', '!=', rec.id)
            ])
            if existing:
                raise ValidationError("Service Part dengan kilometer yang sama sudah ada di perencanaan ini!")