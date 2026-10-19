import re

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class StockMoveLine(models.Model):
    _inherit = 'stock.move.line'

    initial_license_plate = fields.Char(string='Initial License Plate')

    @api.model
    def format_license_plate_input(self, value):
        """Normalize license plate (same rules as x_fleet_document)."""
        if not value:
            return value
        value = value.strip()
        clean = re.sub(r'[^a-zA-Z0-9]', '', value)
        match = re.match(r'^([A-Za-z]{1,2})(\d{1,4})([A-Za-z]{0,3})$', clean)
        if match:
            return f"{match.group(1).upper()} {match.group(2)} {match.group(3).upper()}".strip()
        return value.upper()

    @api.onchange('initial_license_plate')
    def _onchange_format_initial_license_plate(self):
        for line in self:
            if line.initial_license_plate:
                line.initial_license_plate = self.format_license_plate_input(line.initial_license_plate)

    @api.constrains('initial_license_plate')
    def _check_initial_license_plate_format(self):
        pattern = r'^[A-Za-z]{1,2}\s*\d{1,4}\s*[A-Za-z]{0,3}$'
        for line in self:
            if line.initial_license_plate:
                if not re.match(pattern, line.initial_license_plate.strip()):
                    raise ValidationError(
                        _("Invalid License Plate Format!\n"
                          "Correct Format: [1-2 Letters] [1-4 Numbers] [0-3 Letters]\n"
                          "Example: 'B 1234', 'AB 12', or 'B 1234 CD'")
                    )
    chassis_number = fields.Char(string='Chassis Number')
    engine_number = fields.Char(string='Engine Number')
    fleet_brand_id = fields.Many2one(
        'fleet.vehicle.model.brand',
        related='product_id.fleet_brand_id',
        string='Manufacturer',
        readonly=True,
    )
    vehicle_model_id = fields.Many2one(
        'fleet.vehicle.model',
        string='Model',
        domain="[('brand_id', '=', fleet_brand_id)] if fleet_brand_id else []",
    )
    vehicle_year_id = fields.Many2one('vehicle.year', string='Tahun')
    vehicle_color_id = fields.Many2one('vehicle.color', string='Warna')
    analytic_account_id = fields.Many2one(
        'account.analytic.account',
        string='Analytic Account'
    )

    analytic_account_domain_ids = fields.Many2many(
        'account.analytic.account',
        string='Allowed Analytic Accounts',
        compute='_compute_analytic_account_domain_ids',
        store=False,
    )

    @api.depends('product_id', 'product_id.is_vehicle')
    def _compute_analytic_account_domain_ids(self):
        """Allowed analytic accounts: those of the vehicles registered for this product."""
        for line in self:
            if line.product_id and line.product_id.is_vehicle:
                vehicles = self.env['fleet.vehicle'].search([
                    ('lot_id.product_id', '=', line.product_id.id),
                    ('analytic_account_id', '!=', False),
                    # an account of another company cannot be read (nor used) here
                    ('analytic_account_id.company_id', 'in', [False, line.company_id.id]),
                ])
                line.analytic_account_domain_ids = [(6, 0, vehicles.analytic_account_id.ids)]
            else:
                line.analytic_account_domain_ids = [(5, 0, 0)]

    is_fleet_source_locked = fields.Boolean(related='move_id.is_fleet_source_locked')

    is_vehicle = fields.Boolean(
        related='product_id.is_vehicle',
        store=False,
        string='Is Fleet',
    )

    @api.onchange('product_id')
    def _onchange_product_id_reset_model(self):
        for line in self:
            if line.vehicle_model_id and line.fleet_brand_id and line.vehicle_model_id.brand_id != line.fleet_brand_id:
                line.vehicle_model_id = False

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

        self._generate_fleet_number()
        return self.move_id.action_show_details()

    def _generate_fleet_number(self):
        """Give each line a new Fleet Number lot built from its unit data.

        A fleet unit bought on a PO keeps the quantity the user typed (0 until the
        unit is received); any other serial line is set to its single unit.
        """
        Lot = self.env['stock.lot']
        for line in self:
            lot = Lot.create({
                'name': Lot._next_fleet_number(line.company_id),
                'product_id': line.product_id.id,
                'company_id': line.company_id.id,
                'generated_on_receipt': True,
                'initial_license_plate': line.initial_license_plate or '',
                'chassis_number': line.chassis_number or '',
                'engine_number': line.engine_number or '',
                'vehicle_model_id': line.vehicle_model_id.id,
                'vehicle_year_id': line.vehicle_year_id.id,
                'vehicle_color_id': line.vehicle_color_id.id,
                'analytic_account_id': line.analytic_account_id.id,
            })
            vals = {'lot_id': lot.id, 'lot_name': lot.name}
            if not (line.move_id and line.move_id._is_fleet_unit_receipt()):
                vals['quantity'] = 1.0
            line.write(vals)

    @api.onchange('initial_license_plate', 'chassis_number', 'engine_number', 'vehicle_model_id', 'vehicle_year_id', 'vehicle_color_id', 'analytic_account_id')
    def _onchange_sync_vehicle_fields_to_lot(self):
        """Sync vehicle fields ke stock.lot selama unit belum terdaftar sebagai Fleet.

        Setelah lot ter-link ke kendaraan, data unit dikelola dari kendaraan / lot
        (stock_lot.FLEET_LOT_FIELDS); baris GR tidak lagi menimpanya.
        """
        if self.lot_id and not self.lot_id.fleet_vehicle_id:
            self.lot_id.write({
                'initial_license_plate': self.initial_license_plate or '',
                'chassis_number': self.chassis_number or '',
                'engine_number': self.engine_number or '',
                'vehicle_model_id': self.vehicle_model_id.id if self.vehicle_model_id else False,
                'vehicle_year_id': self.vehicle_year_id.id,
                'vehicle_color_id': self.vehicle_color_id.id,
                'analytic_account_id': self.analytic_account_id.id,
            })

    def _get_fleet_vehicle_for_lot(self, lot):
        return lot.sudo().fleet_vehicle_id

    def _resolve_vehicle_year(self, year_name):
        return self.env['vehicle.year']._resolve_by_name(year_name)

    def _resolve_vehicle_color(self, color_name):
        return self.env['vehicle.color']._resolve_by_name(color_name)

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
        """Analytic account of the lot, or of the vehicle linked to it."""
        if lot.analytic_account_id:
            return lot.analytic_account_id
        fleet = self._get_fleet_vehicle_for_lot(lot)
        if 'analytic_account_id' in fleet._fields and fleet.analytic_account_id:
            return fleet.analytic_account_id
        return self.env['account.analytic.account']

    @api.onchange('quant_id')
    def _onchange_quant_id_set_fleet_number(self):
        """Delivery: the unit is picked through "Pick From"; show its data at once."""
        if self.quant_id.lot_id and self.lot_id != self.quant_id.lot_id:
            self.lot_id = self.quant_id.lot_id
            self._onchange_lot_id_load_vehicle_fields()

    @api.onchange('lot_id')
    def _onchange_lot_id_load_vehicle_fields(self):
        """Ketika lot dipilih manual, load data kendaraan dari lot ke line."""
        if self.lot_id:
            lot = self.lot_id
            self.initial_license_plate = lot.initial_license_plate
            self.chassis_number = lot.chassis_number
            self.engine_number = lot.engine_number
            self.vehicle_model_id = self._get_vehicle_model_from_lot(lot)
            self.vehicle_year_id = self._get_vehicle_year_from_lot(lot)
            self.vehicle_color_id = self._get_vehicle_color_from_lot(lot)
            analytic_account = self._get_vehicle_analytic_account_from_lot(lot)
            self.analytic_account_id = analytic_account
            if analytic_account and self.move_id:
                self.move_id._set_asset_analytic_distribution(analytic_account)

    def _get_vehicle_model_from_lot(self, lot):
        if lot.vehicle_model_id:
            return lot.vehicle_model_id
        return self._get_fleet_vehicle_for_lot(lot).model_id

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('initial_license_plate'):
                vals['initial_license_plate'] = self.format_license_plate_input(vals['initial_license_plate'])
            if vals.get('move_id') and (vals.get('lot_id') or vals.get('quant_id')):
                self.env['stock.move'].browse(vals['move_id'])._check_fleet_source_lot(
                    self._fleet_lot_from_vals(vals))
        records = super().create(vals_list)
        records._sync_vehicle_fields_from_lot()
        return records

    def unlink(self):
        # A Fleet Number generated for a unit that is never received (line deleted,
        # "No Backorder", receipt cancelled) must not linger without a unit.
        lots = self.lot_id
        moves = self.move_id
        res = super().unlink()
        lots._unlink_unused_fleet_numbers()
        moves.exists()._sync_fleet_analytic_from_lines()
        return res

    @api.constrains('quantity', 'move_id')
    def _check_fleet_unit_quantity(self):
        for line in self:
            if (line.state not in ('done', 'cancel') and line.move_id
                    and line.move_id._is_fleet_unit_receipt()
                    and line.quantity not in (0.0, 1.0)):
                raise ValidationError(_(
                    'Each vehicle unit line is received with quantity 1, or left at 0 '
                    'for a later receipt (product: %s).', line.product_id.display_name,
                ))

    @api.model
    def _fleet_lot_from_vals(self, vals):
        """Fleet Number a create/write sets, directly or through "Pick From"."""
        if vals.get('quant_id'):
            return self.env['stock.quant'].browse(vals['quant_id']).lot_id
        return self.env['stock.lot'].browse(vals.get('lot_id') or [])

    def write(self, vals):
        if 'lot_id' in vals or vals.get('quant_id'):
            self.move_id._check_fleet_source_lot(self._fleet_lot_from_vals(vals))
        if vals.get('initial_license_plate'):
            vals = dict(vals)
            vals['initial_license_plate'] = self.format_license_plate_input(vals['initial_license_plate'])
        previous_lots = self.lot_id if 'lot_id' in vals else self.env['stock.lot']
        res = super().write(vals)
        if previous_lots:
            (previous_lots - self.lot_id)._unlink_unused_fleet_numbers()
        vehicle_fields = {'initial_license_plate', 'chassis_number', 'engine_number', 'vehicle_model_id', 'vehicle_year_id', 'vehicle_color_id', 'analytic_account_id'}
        if vehicle_fields & set(vals.keys()):
            for line in self:
                # Only while the unit is not registered yet: once its lot is linked to a
                # vehicle, the data is managed there (stock_lot.FLEET_LOT_FIELDS).
                if line.lot_id and not line.lot_id.fleet_vehicle_id:
                    line.lot_id.write({
                        k: vals[k]
                        for k in vehicle_fields & set(vals.keys())
                    })
        # core turns a "Pick From" quant into lot_id inside the same vals
        if 'lot_id' in vals or 'quant_id' in vals:
            self._sync_vehicle_fields_from_lot()
        return res

    def _sync_vehicle_fields_from_lot(self):
        """Copy the unit data and analytic account of the Fleet Number onto the line.

        Once the unit is an existing vehicle (registered, or leaving the stock),
        its Fleet Number is the reference and the line follows it entirely: a
        value the new Fleet Number does not have is cleared, instead of keeping
        the one of the unit chosen before. On a receipt of a new unit, the data
        typed on the line is kept where the Fleet Number has none.
        """
        delivery_moves = self.env['stock.move']
        for line in self:
            if line.move_id and line.move_id._is_fleet_delivery_move():
                delivery_moves |= line.move_id
                if not line.lot_id and line.analytic_account_id:
                    # Fleet Number removed: no unit, no analytic account
                    super(StockMoveLine, line).write({'analytic_account_id': False})
            lot = line.lot_id
            if not lot:
                continue
            follow_lot = bool(lot.sudo().fleet_vehicle_id) or line.picking_code != 'incoming'
            analytic_account = line._get_vehicle_analytic_account_from_lot(lot)
            values = {}
            for fname, value in (
                ('initial_license_plate', lot.initial_license_plate),
                ('chassis_number', lot.chassis_number),
                ('engine_number', lot.engine_number),
                ('vehicle_model_id', line._get_vehicle_model_from_lot(lot)),
                ('vehicle_year_id', line._get_vehicle_year_from_lot(lot)),
                ('vehicle_color_id', line._get_vehicle_color_from_lot(lot)),
                ('analytic_account_id', analytic_account),
            ):
                if (value or follow_lot) and (line[fname] or False) != (value or False):
                    values[fname] = value.id if isinstance(value, models.BaseModel) else (value or False)

            if values:
                super(StockMoveLine, line).write(values)

            if analytic_account and line.move_id not in delivery_moves:
                line.move_id._set_asset_analytic_distribution(analytic_account)
        delivery_moves._sync_fleet_analytic_from_lines()
