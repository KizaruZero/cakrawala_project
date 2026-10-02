import logging
import re

import psycopg2

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)

# Context key set on the counterpart write of a Fleet <-> Lot sync, so that write
# does not bounce the same values back.
FLEET_LOT_SYNC = 'fleet_lot_sync'

# The Fleet <-> Fleet Number bridge, in one place:
# (fleet.vehicle field, stock.lot field, kind, editable from).
# - kind: 'char' / 'm2o' carry the value as is; 'year' / 'color' bridge the free
#   text kept on Fleet with the master-data many2one used on the lot.
# - editable from: 'both' sides once linked, or 'vehicle' only (the lot follows).
# Before a lot is linked to a vehicle every field stays editable on the lot: that
# is where the Goods Receipt captures the unit.
FLEET_LOT_FIELDS = (
    ('chassis_number', 'chassis_number', 'char', 'both'),
    ('engine_number', 'engine_number', 'char', 'both'),
    ('model_id', 'vehicle_model_id', 'm2o', 'both'),
    ('model_year', 'vehicle_year_id', 'year', 'both'),
    ('color', 'vehicle_color_id', 'color', 'both'),
    ('initial_license_plate', 'initial_license_plate', 'char', 'vehicle'),
    ('analytic_account_id', 'analytic_account_id', 'm2o', 'vehicle'),
)


class StockLot(models.Model):
    _inherit = 'stock.lot'

    fleet_vehicle_ids = fields.One2many(
        'fleet.vehicle',
        'lot_id',
        string='Fleet Vehicles',
        context={'active_test': False},
    )
    fleet_vehicle_id = fields.Many2one(
        'fleet.vehicle',
        string='Fleet Vehicle',
        compute='_compute_fleet_vehicle_id',
        store=True,
        index='btree_not_null',
        help='Vehicle registered with this Fleet Number (fleet.vehicle.lot_id).',
    )

    @api.depends('fleet_vehicle_ids')
    def _compute_fleet_vehicle_id(self):
        for lot in self:
            # unique (lot_id) on fleet.vehicle keeps this to one vehicle at most.
            lot.fleet_vehicle_id = lot.fleet_vehicle_ids[:1]

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

    generated_on_receipt = fields.Boolean(
        string='Generated on Goods Receipt',
        readonly=True,
        copy=False,
        help='Fleet Number generated from a Goods Receipt line. It is deleted again '
             'if its unit is never received (line removed, "No Backorder", receipt '
             'cancelled), so that no Fleet Number is left without a unit.',
    )

    # ------------------------------------------------------------------
    # Fleet Number rules
    # ------------------------------------------------------------------
    @api.constrains('name', 'product_id', 'company_id')
    def _check_unique_fleet_number(self):
        """A Fleet Number designates one unit per company, whatever the product.

        Odoo itself only keeps (name, product, company) unique, which let the same
        Fleet Number exist for two different vehicle products.
        """
        fleet_lots = self.filtered(lambda lot: lot.name and lot.product_id.is_vehicle)
        for lot in fleet_lots:
            duplicate = self.sudo().search_count([
                ('id', '!=', lot.id),
                ('name', '=', lot.name),
                ('company_id', '=', lot.company_id.id),
                ('product_id.is_vehicle', '=', True),
            ], limit=1)
            if duplicate:
                raise ValidationError(_(
                    "Fleet Number %(name)s already exists in company %(company)s. "
                    "A Fleet Number must designate a single vehicle.",
                    name=lot.name,
                    company=lot.company_id.display_name or _('(no company)'),
                ))

    @api.model
    def _next_fleet_number(self, company=None):
        """Next Fleet Number from the sequence, skipping numbers already in use.

        A vehicle imported with its Fleet Number waits for a lot of that name, so
        a number handed out by the sequence must never be one of those — or a new
        unit would be linked to the imported vehicle.
        """
        company = company or self.env.company
        Sequence = self.env['ir.sequence'].with_company(company)
        Lot = self.sudo()
        Vehicle = self.env['fleet.vehicle'].sudo().with_context(active_test=False)
        for _attempt in range(100):
            name = Sequence.next_by_code('asset.serial.number')
            if not name:
                raise UserError(_('Sequence for Asset Serial Number is not defined.'))
            in_use = Lot.search_count([
                ('name', '=', name),
                ('company_id', 'in', [company.id, False]),
                ('product_id.is_vehicle', '=', True),
            ], limit=1) or Vehicle.search_count([
                ('asset_number', '=', name),
                ('company_id', 'in', [company.id, False]),
            ], limit=1)
            if not in_use:
                return name
        raise UserError(_('Could not find a free Fleet Number: check the Asset Serial Number sequence.'))

    def _unlink_unused_fleet_numbers(self):
        """Delete Fleet Numbers generated on a receipt whose unit was never received.

        Called when a receipt line lets go of its lot. A lot still on another move
        line, holding stock or linked to a vehicle is kept; so is any lot that was
        not generated by a receipt (created by hand or imported ahead of its vehicle).
        """
        candidates = self.exists().filtered(
            lambda lot: lot.generated_on_receipt and not lot.fleet_vehicle_id
        )
        if not candidates:
            return
        candidates = candidates.sudo()
        in_use = self.env['stock.move.line'].sudo().search([('lot_id', 'in', candidates.ids)]).lot_id
        in_use |= self.env['stock.quant'].sudo().search([('lot_id', 'in', candidates.ids)]).lot_id
        for lot in candidates - in_use:
            name = lot.name
            try:
                with self.env.cr.savepoint():
                    lot.unlink()
            except (UserError, ValidationError, psycopg2.IntegrityError):
                _logger.warning("Unused Fleet Number %s (stock.lot %s) could not be deleted.", name, lot.id, exc_info=True)
            else:
                _logger.info("Unused Fleet Number %s deleted: its unit was not received.", name)

    # ------------------------------------------------------------------
    # Fleet <-> Lot sync
    # ------------------------------------------------------------------
    @api.model
    def _fleet_lot_fields(self, mode=None):
        """The field map, minus whatever this database does not have.

        ``fleet.vehicle.analytic_account_id`` comes from x_fleet_document, which
        depends on this module — so it may legitimately be missing.
        """
        fleet_fields = self.env['fleet.vehicle']._fields
        return tuple(
            entry for entry in FLEET_LOT_FIELDS
            if entry[0] in fleet_fields and (mode is None or entry[3] == mode)
        )

    @api.model
    def _fleet_value_to_lot(self, vehicle, fleet_field, kind):
        value = vehicle[fleet_field]
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

    @api.model
    def _is_valid_model_year(self, value):
        """``fleet.vehicle.model_year`` is a Selection — an unlisted year raises."""
        selection = self.env['fleet.vehicle'].fields_get(
            ['model_year'])['model_year'].get('selection') or []
        return any(str(value) == str(option[0]) for option in selection)

    def _prepare_fleet_vals(self, lot_fields, only_empty_on=None):
        """fleet.vehicle values mirroring ``lot_fields`` of this lot.

        With ``only_empty_on`` (a vehicle), only the fields that vehicle still
        lacks are returned: used when linking, where the vehicle has priority.
        The fleet model is required, so an emptied model never clears it.
        """
        self.ensure_one()
        vals = {}
        for fleet_field, lot_field, kind, _mode in self._fleet_lot_fields():
            if lot_field not in lot_fields:
                continue
            if only_empty_on is not None and only_empty_on[fleet_field]:
                continue
            value = self._lot_value_to_fleet(lot_field, kind)
            if not value and (only_empty_on is not None or fleet_field == 'model_id'):
                continue
            if fleet_field == 'model_year' and value and not self._is_valid_model_year(value):
                continue
            vals[fleet_field] = value
        return vals

    def _check_vehicle_owned_fields(self, vals):
        """Once linked, plate and analytic account change on the vehicle only."""
        if self.env.context.get(FLEET_LOT_SYNC):
            return
        owned = {lot_field: kind for _f, lot_field, kind, _m in self._fleet_lot_fields('vehicle')}
        for lot in self.filtered('fleet_vehicle_id'):
            for lot_field in owned.keys() & vals.keys():
                current = lot[lot_field]
                current = current.id if isinstance(current, models.BaseModel) else current
                if (current or False) != (vals[lot_field] or False):
                    raise UserError(_(
                        "%(field)s of Fleet Number %(lot)s follows vehicle %(vehicle)s: "
                        "change it on the vehicle.",
                        field=self._fields[lot_field].string,
                        lot=lot.name,
                        vehicle=lot.fleet_vehicle_id.display_name,
                    ))

    def _link_waiting_vehicles(self):
        """Link new Fleet Numbers to the vehicles already waiting for them.

        "Fleet first": a vehicle imported with its Fleet Number (asset_number)
        stays unlinked until a lot of that name exists in its company. Linked only
        when exactly one waiting vehicle matches; otherwise the reason goes to the
        lot's chatter and nothing is guessed.
        """
        Vehicle = self.env['fleet.vehicle'].sudo().with_context(active_test=False)
        for lot in self.filtered(lambda l: l.name and l.product_id.is_vehicle and not l.fleet_vehicle_ids):
            domain = [('lot_id', '=', False), ('asset_number', '=', lot.name)]
            if lot.company_id:
                domain.append(('company_id', 'in', [lot.company_id.id, False]))
            vehicles = Vehicle.search(domain, limit=2)
            if len(vehicles) > 1:
                lot.message_post(body=_(
                    'Not linked to a vehicle: several vehicles wait for Fleet Number %s. '
                    'Fix the duplicate, then link the right vehicle.',
                    lot.name,
                ))
            elif vehicles:
                vehicles.write({'lot_id': lot.id})

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('initial_license_plate'):
                vals['initial_license_plate'] = self.env['stock.move.line'].format_license_plate_input(vals['initial_license_plate'])
        lots = super().create(vals_list)
        if not self.env.context.get(FLEET_LOT_SYNC):
            lots._link_waiting_vehicles()
        return lots

    def write(self, vals):
        if vals.get('initial_license_plate'):
            vals = dict(vals)
            vals['initial_license_plate'] = self.env['stock.move.line'].format_license_plate_input(vals['initial_license_plate'])

        syncing = self.env.context.get(FLEET_LOT_SYNC)
        if 'name' in vals and not syncing:
            for lot in self.filtered('fleet_vehicle_id'):
                if lot.name != vals['name']:
                    raise UserError(_(
                        "Fleet Number %(lot)s is linked to vehicle %(vehicle)s and cannot be renamed.",
                        lot=lot.name,
                        vehicle=lot.fleet_vehicle_id.display_name,
                    ))
        self._check_vehicle_owned_fields(vals)

        res = super().write(vals)
        if syncing:
            return res

        two_way = {lot_field for _f, lot_field, _k, _m in self._fleet_lot_fields('both')}
        changed = two_way & vals.keys()
        if changed:
            for lot in self.filtered('fleet_vehicle_id'):
                fleet_vals = lot._prepare_fleet_vals(changed)
                if fleet_vals:
                    lot.fleet_vehicle_id.with_context(**{FLEET_LOT_SYNC: True}).write(fleet_vals)
        if 'name' in vals:
            # A renamed, unlinked lot may now be the one a vehicle waits for.
            self.filtered(lambda l: not l.fleet_vehicle_ids)._link_waiting_vehicles()
        return res
