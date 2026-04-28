from odoo import models, fields, api
from odoo.exceptions import ValidationError

class ServicePlanning(models.Model):
    _name = 'service.planning'
    _description = 'Service Planning'
    _rec_name = 'name'
    _order = 'sequence'

    name = fields.Char(string="Name", readonly=True, default='/')
    vehicle_id = fields.Many2one('fleet.vehicle', string="Vehicle", required=True)
    sequence = fields.Integer(string="Sequence", default=10)
    
    license_plate = fields.Char('License Plate')
    vin_number = fields.Char('VIN Number')
    engine_number = fields.Char('Engine Number')
    asset_number = fields.Char('Asset Number')
    model_year = fields.Char('Year')           

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
                rec.license_plate = rec.vehicle_id.license_plate
                rec.vin_number = rec.vehicle_id.vin_sn
                rec.engine_number = rec.vehicle_id.engine_number
                rec.asset_number = rec.vehicle_id.asset_number
                rec.model_year = rec.vehicle_id.model_year
            else:
                rec.name = '/'
                rec.license_plate = False
                rec.vin_number = False
                rec.engine_number = False
                rec.asset_number = False
                rec.model_year = False

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