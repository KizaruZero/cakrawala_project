from odoo import api, fields, models


class StockLot(models.Model):
    _inherit = 'stock.lot'

    fleet_vehicle_id = fields.Many2one(
        'fleet.vehicle',
        string='Fleet Vehicle',
        compute='_compute_fleet_vehicle_id',
        search='_search_fleet_vehicle_id',
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

    def _search_fleet_vehicle_id(self, operator, value):
        fleets = self.env['fleet.vehicle'].sudo().search([('id', operator, value)])
        return [('name', 'in', fleets.mapped('asset_number'))]

    current_license_plate = fields.Char(
        string='Current License Plate',
        compute='_compute_current_license_plate',
    )

    @api.depends('fleet_vehicle_id', 'fleet_vehicle_id.license_plate')
    def _compute_current_license_plate(self):
        for record in self:
            record.current_license_plate = record.fleet_vehicle_id.license_plate or False

    initial_license_plate = fields.Char(string='Initial License Plate')
    chassis_number = fields.Char(string='Chassis Number')
    engine_number = fields.Char(string='Engine Number')
    vehicle_year_id = fields.Many2one('vehicle.year', string='Tahun')
    vehicle_color_id = fields.Many2one('vehicle.color', string='Warna')

    analytic_account_id = fields.Many2one(
        'account.analytic.account',
        string='Analytic Account',
        readonly=True,
    )

    def _ensure_fleet_sync(self):
        """
        Common synchronization entry-point (Fleet → Lot).

        For every lot whose *name* matches a fleet.vehicle.asset_number,
        pull Fleet data INTO the lot (only fills fields that are still
        empty — never overwrites user-entered values).

        This is intentionally company-agnostic: it searches all
        accessible fleet records so that cross-company scenarios (where
        the lot lives in company A and the fleet in company B) also work.

        Called from:
          • create()  – ensures a newly created lot is immediately synced.
          • write()   – called when the lot name changes.
          • Wizard    – called after a wizard creates a lot for a fleet.
        """
        for lot in self:
            if not lot.name:
                continue
            fleet = self.env['fleet.vehicle'].search(
                [('asset_number', '=', lot.name)], limit=1
            )
            if not fleet:
                continue
            sync_vals = {}
            if fleet.analytic_account_id and not lot.analytic_account_id:
                sync_vals['analytic_account_id'] = fleet.analytic_account_id.id
            if fleet.chassis_number and not lot.chassis_number:
                sync_vals['chassis_number'] = fleet.chassis_number
            if fleet.engine_number and not lot.engine_number:
                sync_vals['engine_number'] = fleet.engine_number
            if fleet.initial_license_plate and not lot.initial_license_plate:
                sync_vals['initial_license_plate'] = fleet.initial_license_plate
            if fleet.model_year and not lot.vehicle_year_id:
                year = self.env['vehicle.year'].search(
                    [('name', '=', fleet.model_year)], limit=1
                )
                if year:
                    sync_vals['vehicle_year_id'] = year.id
            if fleet.color and not lot.vehicle_color_id:
                color = self.env['vehicle.color'].search(
                    [('name', '=', fleet.color)], limit=1
                )
                if color:
                    sync_vals['vehicle_color_id'] = color.id
            if sync_vals:
                lot.with_context(skip_sync_fleet=True).write(sync_vals)

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        if self._context.get('skip_sync_fleet'):
            return records

        records._ensure_fleet_sync()

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


        if 'name' in vals:
            self._ensure_fleet_sync()

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
