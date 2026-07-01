from odoo import api, fields, models, _
from odoo.exceptions import UserError


class StockMoveLine(models.Model):
    _inherit = 'stock.move.line'

    initial_license_plate = fields.Char(string='Initial License Plate')
    chassis_number = fields.Char(string='Chassis Number')
    engine_number = fields.Char(string='Engine Number')
    vehicle_year_id = fields.Many2one('vehicle.year', string='Tahun')
    vehicle_color_id = fields.Many2one('vehicle.color', string='Warna')
    analytic_account_id = fields.Many2one(
        'account.analytic.account',
        string='Analytic Account'
    )

    is_vehicle = fields.Boolean(
        related='product_id.is_vehicle',
        store=False,
        string='Is Vehicle',
    )

    def action_generate_serial_number_line(self):
        """Generate SN untuk baris move line ini saja."""
        self.ensure_one()

        if self.product_id.tracking != 'serial':
            raise UserError(
                _('Product %s is not tracked by serial number.')
                % self.product_id.display_name
            )

        if self.lot_id:
            raise UserError(
                _('This line already has a Serial Number (%s). '
                  'Delete it first to generate a new one.')
                % self.lot_id.name
            )

        sequence = self.env['ir.sequence'].next_by_code('asset.serial.number')
        if not sequence:
            raise UserError(_('Sequence for Asset Serial Number is not defined.'))

        lot = self.env['stock.lot'].create({
            'name': sequence,
            'product_id': self.product_id.id,
            'company_id': self.company_id.id,
            'initial_license_plate': self.initial_license_plate or '',
            'chassis_number': self.chassis_number or '',
            'engine_number': self.engine_number or '',
            'vehicle_year_id': self.vehicle_year_id.id,
            'vehicle_color_id': self.vehicle_color_id.id,
            'analytic_account_id': self.analytic_account_id.id,
        })

        self.write({
            'lot_id': lot.id,
            'lot_name': lot.name,
            'quantity': 1.0,
        })

        return self.move_id.action_show_details()

    @api.onchange('initial_license_plate', 'chassis_number', 'engine_number', 'vehicle_year_id', 'vehicle_color_id', 'analytic_account_id')
    def _onchange_sync_vehicle_fields_to_lot(self):
        """Sync vehicle fields ke stock.lot jika lot sudah ada."""
        if self.lot_id:
            self.lot_id.write({
                'initial_license_plate': self.initial_license_plate or '',
                'chassis_number': self.chassis_number or '',
                'engine_number': self.engine_number or '',
                'vehicle_year_id': self.vehicle_year_id.id,
                'vehicle_color_id': self.vehicle_color_id.id,
                'analytic_account_id': self.analytic_account_id.id,
            })

    def _get_fleet_vehicle_for_lot(self, lot):
        if not lot.name:
            return self.env['fleet.vehicle']
        return self.env['fleet.vehicle'].search([('asset_number', '=', lot.name)], limit=1)

    def _resolve_vehicle_year(self, year_name):
        if not year_name:
            return self.env['vehicle.year']
        return self.env['vehicle.year'].search([('name', '=', year_name)], limit=1)

    def _resolve_vehicle_color(self, color_name):
        if not color_name:
            return self.env['vehicle.color']
        return self.env['vehicle.color'].search([('name', '=', color_name)], limit=1)

    def _get_vehicle_year_from_lot(self, lot):
        if lot.vehicle_year_id:
            return lot.vehicle_year_id
        fleet = self._get_fleet_vehicle_for_lot(lot)
        if fleet.model_year:
            return self._resolve_vehicle_year(fleet.model_year)
        return self.env['vehicle.year']

    def _get_vehicle_color_from_lot(self, lot):
        if lot.vehicle_color_id:
            return lot.vehicle_color_id
        fleet = self._get_fleet_vehicle_for_lot(lot)
        if fleet.color:
            return self._resolve_vehicle_color(fleet.color)
        return self.env['vehicle.color']

    def _get_vehicle_analytic_account_from_lot(self, lot):
        """Resolve analytic account from lot, or from linked fleet vehicle by asset number."""
        if lot.analytic_account_id:
            return lot.analytic_account_id
        if lot.name and 'analytic_account_id' in self.env['fleet.vehicle']._fields:
            fleet = self.env['fleet.vehicle'].search([('asset_number', '=', lot.name)], limit=1)
            if fleet.analytic_account_id:
                return fleet.analytic_account_id
        return self.env['account.analytic.account']

    @api.onchange('lot_id')
    def _onchange_lot_id_load_vehicle_fields(self):
        """Ketika lot dipilih manual, load data kendaraan dari lot ke line."""
        if self.lot_id:
            lot = self.lot_id
            self.initial_license_plate = lot.initial_license_plate
            self.chassis_number = lot.chassis_number
            self.engine_number = lot.engine_number
            self.vehicle_year_id = self._get_vehicle_year_from_lot(lot)
            self.vehicle_color_id = self._get_vehicle_color_from_lot(lot)
            analytic_account = self._get_vehicle_analytic_account_from_lot(lot)
            self.analytic_account_id = analytic_account
            if analytic_account and self.move_id:
                self.move_id._set_asset_analytic_distribution(analytic_account)

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._sync_vehicle_fields_from_lot()
        return records

    def write(self, vals):
        res = super().write(vals)
        vehicle_fields = {'initial_license_plate', 'chassis_number', 'engine_number', 'vehicle_year_id', 'vehicle_color_id', 'analytic_account_id'}
        if vehicle_fields & set(vals.keys()):
            for line in self:
                if line.lot_id:
                    line.lot_id.write({
                        k: vals[k]
                        for k in vehicle_fields & set(vals.keys())
                    })
        if 'lot_id' in vals:
            self._sync_vehicle_fields_from_lot()
        return res

    def _sync_vehicle_fields_from_lot(self):
        for line in self.filtered(lambda l: l.lot_id):
            lot = line.lot_id
            values = {}
            if lot.initial_license_plate and line.initial_license_plate != lot.initial_license_plate:
                values['initial_license_plate'] = lot.initial_license_plate
            if lot.chassis_number and line.chassis_number != lot.chassis_number:
                values['chassis_number'] = lot.chassis_number
            if lot.engine_number and line.engine_number != lot.engine_number:
                values['engine_number'] = lot.engine_number

            vehicle_year = line._get_vehicle_year_from_lot(lot)
            if vehicle_year and line.vehicle_year_id != vehicle_year:
                values['vehicle_year_id'] = vehicle_year.id

            vehicle_color = line._get_vehicle_color_from_lot(lot)
            if vehicle_color and line.vehicle_color_id != vehicle_color:
                values['vehicle_color_id'] = vehicle_color.id

            analytic_account = line._get_vehicle_analytic_account_from_lot(lot)
            if analytic_account and line.analytic_account_id != analytic_account:
                values['analytic_account_id'] = analytic_account.id

            if values:
                super(StockMoveLine, line).write(values)

            if analytic_account and line.move_id:
                line.move_id._set_asset_analytic_distribution(analytic_account)
