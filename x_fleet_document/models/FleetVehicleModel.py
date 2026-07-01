from odoo import _, fields, models, api


class FleetVehicle(models.Model):
    _inherit = 'fleet.vehicle'

    license_plate_history_ids = fields.One2many(
        'fleet.vehicle.license.plate.history',
        'vehicle_id',
        string='License Plate History',
        readonly=True,
    )

    sub_type = fields.Char(string='Sub Type')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('license_plate') and vals.get('initial_license_plate'):
                vals['license_plate'] = vals['initial_license_plate']
        records = super().create(vals_list)
        History = self.env['fleet.vehicle.license.plate.history']
        for record in records:
            if record.license_plate:
                History.create({
                    'vehicle_id': record.id,
                    'license_plate': record.license_plate,
                    'valid_from': None,
                    'valid_until': None,
                })
        return records

    def write(self, vals):
        if 'license_plate' in vals:
            old_plates = {rec.id: rec.license_plate for rec in self}
        result = super().write(vals)
        if 'license_plate' in vals and not self.env.context.get('x_skip_plate_history'):
            History = self.env['fleet.vehicle.license.plate.history']
            new_plate = vals['license_plate']
            today = fields.Date.today()
            for rec in self:
                old_plate = old_plates.get(rec.id)
                if old_plate != new_plate and new_plate:
                    last = History.search([
                        ('vehicle_id', '=', rec.id),
                        ('license_plate', '=', old_plate),
                        ('valid_until', '=', False),
                    ], limit=1, order='id desc')
                    if last:
                        last.valid_until = today
                    History.create({
                        'vehicle_id': rec.id,
                        'license_plate': new_plate,
                        'valid_from': None,
                        'valid_until': None,
                    })
        return result

