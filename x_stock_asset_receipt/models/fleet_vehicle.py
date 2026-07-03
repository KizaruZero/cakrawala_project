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

    fleet_vehicle_lot_id = fields.Many2one(
        'stock.lot',
        string='Serial Number',
        compute='_compute_fleet_vehicle_lot_id',
        store=False,
        help='The Stock Lot (Serial Number) whose name matches this vehicle\'s Asset Number. '
             'This is the Product ↔ Fleet bridge.',
    )

    @api.depends('asset_number')
    def _compute_fleet_vehicle_lot_id(self):
        for vehicle in self:
            if vehicle.asset_number:
                lot = self.env['stock.lot'].search(
                    [('name', '=', vehicle.asset_number)], limit=1
                )
                vehicle.fleet_vehicle_lot_id = lot
            else:
                vehicle.fleet_vehicle_lot_id = False

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        if self._context.get('skip_sync_lot'):
            return records
            
        for record in records:
            if record.asset_number and (
                record.chassis_number or record.engine_number or record.initial_license_plate
                or record.analytic_account_id or record.model_year or record.color
            ):
                lots = self.env['stock.lot'].search([('name', '=', record.asset_number)])
                if lots:
                    sync_vals = {}
                    if record.chassis_number:
                        sync_vals['chassis_number'] = record.chassis_number
                    if record.engine_number:
                        sync_vals['engine_number'] = record.engine_number
                    if record.initial_license_plate:
                        sync_vals['initial_license_plate'] = record.initial_license_plate
                    if record.analytic_account_id:
                        sync_vals['analytic_account_id'] = record.analytic_account_id.id
                    if record.model_year:
                        year = self.env['vehicle.year'].search([('name', '=', record.model_year)], limit=1)
                        if year:
                            sync_vals['vehicle_year_id'] = year.id
                    if record.color:
                        color = self.env['vehicle.color'].search([('name', '=', record.color)], limit=1)
                        if color:
                            sync_vals['vehicle_color_id'] = color.id

                    if sync_vals:
                        lots.with_context(skip_sync_fleet=True).write(sync_vals)
        return records

    def write(self, vals):
        res = super().write(vals)
        if self._context.get('skip_sync_lot'):
            return res

        tracked_fields = {
            'chassis_number', 'engine_number', 'initial_license_plate',
            'analytic_account_id', 'model_year', 'color', 'asset_number',
        }
        if not tracked_fields.intersection(vals):
            return res

        for record in self:
            if not record.asset_number:
                continue
            lots = self.env['stock.lot'].search([('name', '=', record.asset_number)])
            if not lots:
                continue

            sync_vals = {}
            if 'chassis_number' in vals:
                sync_vals['chassis_number'] = record.chassis_number
            if 'engine_number' in vals:
                sync_vals['engine_number'] = record.engine_number
            if 'initial_license_plate' in vals:
                sync_vals['initial_license_plate'] = record.initial_license_plate
            if 'analytic_account_id' in vals:
                sync_vals['analytic_account_id'] = record.analytic_account_id.id
            if 'model_year' in vals and record.model_year:
                year = self.env['vehicle.year'].search([('name', '=', record.model_year)], limit=1)
                if year:
                    sync_vals['vehicle_year_id'] = year.id
            if 'color' in vals and record.color:
                color = self.env['vehicle.color'].search([('name', '=', record.color)], limit=1)
                if color:
                    sync_vals['vehicle_color_id'] = color.id

            if sync_vals:
                lots.with_context(skip_sync_fleet=True).write(sync_vals)
        return res
