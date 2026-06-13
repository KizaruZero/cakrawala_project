from odoo import api, models, fields


class FleetVehicle(models.Model):
    _inherit = 'fleet.vehicle'

    fleet_sub_status_id = fields.Many2one(
        'vehicle.substatus',
        string='Fleet Sub-Status',
        ondelete='restrict',
    )
    asset_type = fields.Char(string='Asset Type')
    asset_number = fields.Char(string='Asset Number')
    unit_classification = fields.Char(string='Unit Classification')
    assignment_date = fields.Date(string='Assignment Date')
    plan_to_disposal = fields.Boolean(string='Plan to Disposal')
    initial_license_plate = fields.Char(string='Initial License Plate')
    chassis_number = fields.Char(string='Chassis Number')
    engine_number = fields.Char(string='Engine Number')

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        if self._context.get('skip_sync_lot'):
            return records
            
        for record in records:
            if record.asset_number and (record.chassis_number or record.engine_number):
                lots = self.env['stock.lot'].search([('name', '=', record.asset_number)])
                if lots:
                    lots.with_context(skip_sync_fleet=True).write({
                        'chassis_number': record.chassis_number or lots[0].chassis_number,
                        'engine_number': record.engine_number or lots[0].engine_number,
                    })
        return records

    def write(self, vals):
        res = super().write(vals)
        if self._context.get('skip_sync_lot'):
            return res
            
        if 'chassis_number' in vals or 'engine_number' in vals or 'asset_number' in vals:
            for record in self:
                if record.asset_number:
                    lots = self.env['stock.lot'].search([('name', '=', record.asset_number)])
                    if lots:
                        sync_vals = {}
                        if 'chassis_number' in vals:
                            sync_vals['chassis_number'] = record.chassis_number
                        if 'engine_number' in vals:
                            sync_vals['engine_number'] = record.engine_number
                            
                        if sync_vals:
                            lots.with_context(skip_sync_fleet=True).write(sync_vals)
        return res
