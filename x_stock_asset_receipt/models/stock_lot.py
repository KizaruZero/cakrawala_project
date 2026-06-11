from odoo import api, fields, models


class StockLot(models.Model):
    _inherit = 'stock.lot'

    initial_license_plate = fields.Char(string='Initial License Plate')
    chassis_number = fields.Char(string='Chassis Number')
    engine_number = fields.Char(string='Engine Number')
    vehicle_year_id = fields.Many2one('vehicle.year', string='Tahun')
    vehicle_color_id = fields.Many2one('vehicle.color', string='Warna')

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        if self._context.get('skip_sync_fleet'):
            return records
            
        for record in records:
            if record.name and (record.chassis_number or record.engine_number or record.initial_license_plate):
                fleets = self.env['fleet.vehicle'].search([('asset_number', '=', record.name)])
                if fleets:
                    sync_vals = {}
                    if record.chassis_number:
                        sync_vals['chassis_number'] = record.chassis_number
                    if record.engine_number:
                        sync_vals['engine_number'] = record.engine_number
                    if record.initial_license_plate:
                        sync_vals['initial_license_plate'] = record.initial_license_plate
                        
                    if sync_vals:
                        fleets.with_context(skip_sync_lot=True).write(sync_vals)
        return records

    def write(self, vals):
        old_fleets = {}
        if not self._context.get('skip_sync_fleet'):
            if 'name' in vals or 'chassis_number' in vals or 'engine_number' in vals or 'initial_license_plate' in vals:
                for record in self:
                    if record.name:
                        fleets = self.env['fleet.vehicle'].search([('asset_number', '=', record.name)])
                        if fleets:
                            old_fleets[record.id] = fleets
                            
        res = super().write(vals)
        if self._context.get('skip_sync_fleet'):
            return res
            
        for record in self:
            fleets = old_fleets.get(record.id)
            if fleets:
                sync_vals = {}
                if 'name' in vals:
                    sync_vals['asset_number'] = record.name
                if 'chassis_number' in vals:
                    sync_vals['chassis_number'] = record.chassis_number
                if 'engine_number' in vals:
                    sync_vals['engine_number'] = record.engine_number
                if 'initial_license_plate' in vals:
                    sync_vals['initial_license_plate'] = record.initial_license_plate
                    
                if sync_vals:
                    fleets.with_context(skip_sync_lot=True).write(sync_vals)
        return res
