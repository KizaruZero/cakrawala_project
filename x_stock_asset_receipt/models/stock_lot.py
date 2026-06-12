from odoo import api, fields, models


class StockLot(models.Model):
    _inherit = 'stock.lot'

    initial_license_plate = fields.Char(string='Initial License Plate')
    chassis_number = fields.Char(string='Chassis Number')
    engine_number = fields.Char(string='Engine Number')
    vehicle_year_id = fields.Many2one('vehicle.year', string='Tahun')
    vehicle_color_id = fields.Many2one('vehicle.color', string='Warna')

    @api.onchange('name')
    def _onchange_name_warning(self):
        for record in self:
            if record._origin.id and record.name != record._origin.name:
                fleet = self.env['fleet.vehicle'].search([('asset_number', '=', record._origin.name)], limit=1)
                if fleet:
                    return {
                        'warning': {
                            'title': "Asset Number Change Warning",
                            'message': "Are you sure you want to change this Lot/Serial Number? This data is currently connected to Fleet Vehicle with Asset Number: %s" % record._origin.name
                        }
                    }

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        if self._context.get('skip_sync_fleet'):
            return records
            
        for record in records:
            if record.name and (record.chassis_number or record.engine_number):
                fleets = self.env['fleet.vehicle'].search([('asset_number', '=', record.name)])
                if fleets:
                    fleets.with_context(skip_sync_lot=True).write({
                        'chassis_number': record.chassis_number or fleets[0].chassis_number,
                        'engine_number': record.engine_number or fleets[0].engine_number,
                    })
        return records

    def write(self, vals):
        res = super().write(vals)
        if self._context.get('skip_sync_fleet'):
            return res
            
        if 'chassis_number' in vals or 'engine_number' in vals or 'name' in vals:
            for record in self:
                if record.name:
                    fleets = self.env['fleet.vehicle'].search([('asset_number', '=', record.name)])
                    if fleets:
                        sync_vals = {}
                        if 'chassis_number' in vals:
                            sync_vals['chassis_number'] = record.chassis_number
                        if 'engine_number' in vals:
                            sync_vals['engine_number'] = record.engine_number
                            
                        if sync_vals:
                            fleets.with_context(skip_sync_lot=True).write(sync_vals)
        return res
