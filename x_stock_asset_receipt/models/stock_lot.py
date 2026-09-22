import re

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class StockLot(models.Model):
    _inherit = 'stock.lot'

    # The Fleet <-> Lot bridge, in one place: (fleet.vehicle field, stock.lot
    # field, kind). 'char' and 'm2o' carry the value across unchanged; 'year'
    # and 'color' bridge the free text stored on Fleet with the master-data
    # many2one used on the lot.
    _FLEET_SYNC_FIELDS = (
        ('chassis_number', 'chassis_number', 'char'),
        ('engine_number', 'engine_number', 'char'),
        ('initial_license_plate', 'initial_license_plate', 'char'),
        ('model_id', 'vehicle_model_id', 'm2o'),
        ('model_year', 'vehicle_year_id', 'year'),
        ('color', 'vehicle_color_id', 'color'),
        ('analytic_account_id', 'analytic_account_id', 'm2o'),
    )

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
            record.fleet_vehicle_id = record._matching_fleet_vehicles()[:1]

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

    @api.onchange('initial_license_plate')
    def _onchange_format_initial_license_plate(self):
        for record in self:
            if record.initial_license_plate:
                record.initial_license_plate = self.env['stock.move.line'].format_license_plate_input(record.initial_license_plate)

    @api.constrains('initial_license_plate')
    def _check_initial_license_plate_format(self):
        pattern = r'^[A-Za-z]{1,2}\s*\d{1,4}\s*[A-Za-z]{0,3}$'
        for record in self:
            if record.initial_license_plate:
                if not re.match(pattern, record.initial_license_plate.strip()):
                    raise ValidationError(
                        _("Invalid License Plate Format!\n"
                          "Correct Format: [1-2 Letters] [1-4 Numbers] [0-3 Letters]\n"
                          "Example: 'B 1234', 'AB 12', or 'B 1234 CD'")
                    )

    chassis_number = fields.Char(string='Chassis Number')
    engine_number = fields.Char(string='Engine Number')
    vehicle_model_id = fields.Many2one('fleet.vehicle.model', string='Model')
    vehicle_year_id = fields.Many2one('vehicle.year', string='Tahun')
    vehicle_color_id = fields.Many2one('vehicle.color', string='Warna')

    analytic_account_id = fields.Many2one(
        'account.analytic.account',
        string='Analytic Account',
        readonly=True,
    )

    # ------------------------------------------------------------------
    # Fleet <-> Lot bridge
    # ------------------------------------------------------------------
    @api.model
    def _fleet_sync_fields(self):
        """The field map, minus whatever this database does not have.

        ``fleet.vehicle.analytic_account_id`` is added by x_fleet_document,
        which depends on this module — so it may legitimately be missing.
        """
        fleet_fields = self.env['fleet.vehicle']._fields
        return tuple(
            entry for entry in self._FLEET_SYNC_FIELDS if entry[0] in fleet_fields
        )

    def _matching_fleet_vehicles(self):
        """Vehicles bridged to this lot through Fleet Number == lot name.

        sudo: the bridge has to hold for whoever touches the record. An
        Inventory user creating a serial number has no Fleet access, and a Fleet
        user has no Lot access — without this, the lookup quietly returned
        nothing and the two sides stayed out of sync.

        Deliberately company-agnostic, so a lot in one company still finds its
        vehicle in another.
        """
        self.ensure_one()
        if not self.name:
            return self.env['fleet.vehicle']
        return self.env['fleet.vehicle'].sudo().search(
            [('asset_number', '=', self.name)]
        )

    @api.model
    def _fleet_value_to_lot(self, fleet, fleet_field, kind):
        value = fleet[fleet_field]
        if kind == 'char':
            return value or False
        if kind == 'm2o':
            return value.id if value else False
        if kind == 'year':
            return self.env['vehicle.year']._resolve_by_name(value).id or False
        if kind == 'color':
            return self.env['vehicle.color']._resolve_by_name(value).id or False
        return False

    def _lot_value_to_fleet(self, lot_field, kind):
        self.ensure_one()
        value = self[lot_field]
        if kind == 'char':
            return value or False
        if kind == 'm2o':
            return value.id if value else False
        if kind in ('year', 'color'):
            return value.name or False
        return False

    def _lot_current_value(self, lot_field, kind):
        self.ensure_one()
        value = self[lot_field]
        if kind == 'char':
            return value or False
        return value.id if value else False

    @api.model
    def _fleet_current_value(self, fleet, fleet_field, kind):
        value = fleet[fleet_field]
        if kind == 'm2o':
            return value.id if value else False
        return value or False

    @api.model
    def _is_valid_model_year(self, value):
        """``fleet.vehicle.model_year`` is a Selection — an unlisted year raises."""
        selection = self.env['fleet.vehicle'].fields_get(
            ['model_year'])['model_year'].get('selection') or []
        return any(str(value) == str(option[0]) for option in selection)

    def _fleet_to_lot_vals(self, fleet, forced_lot_fields=()):
        """Values to copy Fleet -> this lot.

        ``forced_lot_fields`` are the ones just edited on the vehicle: they are
        mirrored verbatim, clearing included. Every other mapped field is
        *backfilled* — written only while the lot still has nothing — so a value
        typed on the lot is never silently replaced, yet a field that never
        arrived (lot created before the vehicle existed, or written with the
        sync skipped) catches up. That backfill is what makes one edit repair
        the whole record instead of only the edited field.
        """
        self.ensure_one()
        vals = {}
        for fleet_field, lot_field, kind in self._fleet_sync_fields():
            new_value = self._fleet_value_to_lot(fleet, fleet_field, kind)
            current = self._lot_current_value(lot_field, kind)
            if lot_field not in forced_lot_fields:
                if current or not new_value:
                    continue
            if new_value == current:
                continue
            vals[lot_field] = new_value
        return vals

    def _lot_to_fleet_vals(self, fleet, forced_fleet_fields=()):
        """Values to copy this lot -> Fleet, mirroring ``_fleet_to_lot_vals``."""
        self.ensure_one()
        vals = {}
        for fleet_field, lot_field, kind in self._fleet_sync_fields():
            new_value = self._lot_value_to_fleet(lot_field, kind)
            if fleet_field == 'model_year' and new_value and not self._is_valid_model_year(new_value):
                continue
            current = self._fleet_current_value(fleet, fleet_field, kind)
            if fleet_field not in forced_fleet_fields:
                if current or not new_value:
                    continue
            if new_value == current:
                continue
            vals[fleet_field] = new_value
        return vals

    def _write_lot_from_fleet(self, forced_lot_fields=(), fleet=None):
        """Fleet -> Lot. ``fleet`` pins the source when the vehicle drives it."""
        for lot in self:
            vehicle = fleet if fleet is not None else lot._matching_fleet_vehicles()[:1]
            if not vehicle:
                continue
            vals = lot._fleet_to_lot_vals(vehicle, forced_lot_fields)
            if vals:
                lot.with_context(skip_sync_fleet=True).sudo().write(vals)

    def _write_fleet_from_lot(self, forced_fleet_fields=()):
        """Lot -> Fleet, for every vehicle sharing this Fleet Number."""
        for lot in self:
            for vehicle in lot._matching_fleet_vehicles():
                vals = lot._lot_to_fleet_vals(vehicle, forced_fleet_fields)
                if vals:
                    vehicle.with_context(skip_sync_lot=True).write(vals)

    def _ensure_fleet_sync(self):
        """Pull Fleet data into the lot, filling whatever is still empty.

        Kept as the module's public entry point (create, rename, migration).
        """
        self._write_lot_from_fleet()

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('initial_license_plate'):
                vals['initial_license_plate'] = self.env['stock.move.line'].format_license_plate_input(vals['initial_license_plate'])
        records = super().create(vals_list)
        if self.env.context.get('skip_sync_fleet'):
            return records

        sync_map = self._fleet_sync_fields()
        for record, vals in zip(records, vals_list):
            # Fleet first, so a serial created against an imported vehicle comes
            # out complete...
            record._ensure_fleet_sync()
            # ...then push back what was typed on the lot itself, which wins over
            # the vehicle because the user just entered it.
            forced = {
                fleet_field
                for fleet_field, lot_field, _kind in sync_map
                if vals.get(lot_field)
            }
            record._write_fleet_from_lot(forced_fleet_fields=forced)
        return records

    def write(self, vals):
        if vals.get('initial_license_plate'):
            vals = dict(vals)
            vals['initial_license_plate'] = self.env['stock.move.line'].format_license_plate_input(vals['initial_license_plate'])

        if self.env.context.get('skip_sync_fleet'):
            return super().write(vals)

        sync_map = self._fleet_sync_fields()
        forced_fleet_fields = {
            fleet_field for fleet_field, lot_field, _kind in sync_map if lot_field in vals
        }

        # A rename has to reach the vehicle matching the OLD name, so resolve it
        # before the write goes through.
        previous_fleets = {}
        if 'name' in vals:
            for lot in self:
                previous_fleets[lot.id] = lot._matching_fleet_vehicles()

        res = super().write(vals)

        if 'name' in vals:
            for lot in self:
                for vehicle in previous_fleets.get(lot.id, self.env['fleet.vehicle']):
                    vehicle.with_context(skip_sync_lot=True).write({'asset_number': lot.name})

        if forced_fleet_fields or 'name' in vals:
            self._write_fleet_from_lot(forced_fleet_fields=forced_fleet_fields)
            # Re-check every mapped field, not just the edited one: anything the
            # lot is still missing is taken from the vehicle here.
            self._write_lot_from_fleet()
        return res
