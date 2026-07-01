from odoo import api, fields, models


class StockLot(models.Model):
    _inherit = 'stock.lot'

    # --- Fleet Reference (readonly, computed from asset_number / lot name) ---
    fleet_vehicle_id = fields.Many2one(
        'fleet.vehicle',
        string='Fleet Vehicle',
        compute='_compute_fleet_vehicle_id',
        store=True,
        readonly=True,
    )

    @api.depends('name')
    def _compute_fleet_vehicle_id(self):
        for record in self:
            if record.name:
                fleet = self.env['fleet.vehicle'].search(
                    [('asset_number', '=', record.name)], limit=1
                )
                record.fleet_vehicle_id = fleet
            else:
                record.fleet_vehicle_id = False

    # --- Current license plate (live from fleet master) ---
    current_license_plate = fields.Char(
        string='Current License Plate',
        compute='_compute_current_license_plate',
    )

    @api.depends('fleet_vehicle_id', 'fleet_vehicle_id.license_plate')
    def _compute_current_license_plate(self):
        for record in self:
            record.current_license_plate = record.fleet_vehicle_id.license_plate or False

    # --- Vehicle detail fields (bidirectional sync dengan fleet.vehicle) ---
    initial_license_plate = fields.Char(string='Initial License Plate')
    chassis_number = fields.Char(string='Chassis Number')
    engine_number = fields.Char(string='Engine Number')
    vehicle_year_id = fields.Many2one('vehicle.year', string='Tahun')
    vehicle_color_id = fields.Many2one('vehicle.color', string='Warna')

    # --- Analytic Account: readonly, hanya di-sync DARI fleet.vehicle ---
    analytic_account_id = fields.Many2one(
        'account.analytic.account',
        string='Analytic Account',
        readonly=True,
    )

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        if self._context.get('skip_sync_fleet'):
            return records

        for record in records:
            if record.name and (
                record.chassis_number or record.engine_number or record.initial_license_plate
                or record.vehicle_year_id or record.vehicle_color_id
            ):
                fleets = self.env['fleet.vehicle'].search([('asset_number', '=', record.name)])
                if fleets:
                    sync_vals = {}
                    if record.chassis_number:
                        sync_vals['chassis_number'] = record.chassis_number
                    if record.engine_number:
                        sync_vals['engine_number'] = record.engine_number
                    if record.initial_license_plate:
                        sync_vals['initial_license_plate'] = record.initial_license_plate
                    if record.vehicle_year_id:
                        sync_vals['model_year'] = record.vehicle_year_id.name
                    if record.vehicle_color_id:
                        sync_vals['color'] = record.vehicle_color_id.name

                    if sync_vals:
                        fleets.with_context(skip_sync_lot=True).write(sync_vals)
        return records

    def write(self, vals):
        old_fleets = {}
        if not self._context.get('skip_sync_fleet'):
            tracked = {
                'name', 'chassis_number', 'engine_number',
                'initial_license_plate', 'vehicle_year_id', 'vehicle_color_id',
            }
            if tracked.intersection(vals):
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
                if 'vehicle_year_id' in vals and record.vehicle_year_id:
                    sync_vals['model_year'] = record.vehicle_year_id.name
                if 'vehicle_color_id' in vals and record.vehicle_color_id:
                    sync_vals['color'] = record.vehicle_color_id.name

                if sync_vals:
                    fleets.with_context(skip_sync_lot=True).write(sync_vals)
        return res
