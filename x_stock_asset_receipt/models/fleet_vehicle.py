from odoo import _, api, models, fields
from odoo.exceptions import UserError, ValidationError

from .stock_lot import FLEET_LOT_SYNC


class FleetVehicle(models.Model):
    _inherit = 'fleet.vehicle'

    def action_open_fleet_vehicles(self):
        """Smart-button redirect for the vehicles in ``self``.

        Standard Odoo behaviour: a single vehicle opens straight on its form,
        several open the list filtered on them. Shared by the Purchase Order and
        Goods Receipt smart buttons so both stay consistent.
        """
        action = self.env['ir.actions.actions']._for_xml_id('fleet.fleet_vehicle_action')
        action['name'] = _('Fleet / Vehicles')
        if len(self) == 1:
            action['views'] = [(self.env.ref('fleet.fleet_vehicle_view_form').id, 'form')]
            action['res_id'] = self.id
            action['context'] = {
                'active_id': self.id,
                'active_ids': [self.id],
                'active_model': 'fleet.vehicle',
            }
        else:
            action['views'] = [(False, 'list'), (False, 'form')]
            action['domain'] = [('id', 'in', self.ids)]
            action['context'] = {
                'active_ids': self.ids,
                'active_model': 'fleet.vehicle',
            }
        return action

    fleet_sub_status_id = fields.Many2one(
        'vehicle.substatus',
        string='Fleet Sub-Status',
        ondelete='restrict',
        domain="['|', ('state_id', '=', False), ('state_id', '=', state_id)]",
    )

    @api.constrains('state_id', 'fleet_sub_status_id')
    def _check_fleet_sub_status_mapping(self):
        """Status / Sub-Status mapping (Master Sub Status > Parent Status)."""
        for vehicle in self:
            parent = vehicle.fleet_sub_status_id.state_id
            if parent and vehicle.state_id != parent:
                raise ValidationError(_(
                    "Sub-Status '%(sub)s' belongs to Status '%(parent)s', but vehicle %(vehicle)s "
                    "is in Status '%(state)s'. Change the Status and Sub-Status together.",
                    sub=vehicle.fleet_sub_status_id.name,
                    parent=parent.name,
                    vehicle=vehicle.display_name,
                    state=vehicle.state_id.name or _('(none)'),
                ))

    @api.onchange('state_id')
    def _onchange_state_id_clear_sub_status(self):
        parent = self.fleet_sub_status_id.state_id
        if parent and parent != self.state_id:
            self.fleet_sub_status_id = False

    def _set_fleet_status(self, sub_status=None, state=None):
        """Single entry point for automated Status / Sub-Status changes.

        Both fields are written in one call so the mapping constraint never sees a
        half-updated vehicle.
        - ``sub_status`` given: the status follows its Parent Status (``state`` is only
          used for sub-statuses without a parent).
        - only ``state`` given: the current sub-status is cleared when it belongs to
          another status.
        """
        if sub_status:
            vals = {'fleet_sub_status_id': sub_status.id}
            target_state = sub_status.state_id or state
            if target_state:
                vals['state_id'] = target_state.id
            return self.write(vals)
        if not state:
            return True
        for vehicle in self:
            vals = {'state_id': state.id}
            parent = vehicle.fleet_sub_status_id.state_id
            if parent and parent != state:
                vals['fleet_sub_status_id'] = False
            vehicle.write(vals)
        return True
    asset_type = fields.Char(string='Asset Type (Legacy)', help='Kept for Odoo Studio backward compatibility')
    asset_number = fields.Char(
        string='Asset Number',
        help='Fleet Number of the vehicle. Follows the linked Fleet Number (lot); '
             'on a vehicle without one yet (e.g. imported), the number it waits for.',
    )
    unit_classification = fields.Char(string='Unit Classification')
    assignment_date = fields.Date(string='Assignment Date (Asset)')
    plan_to_disposal = fields.Boolean(string='Plan to Disposal')
    initial_license_plate = fields.Char(string='Initial License Plate')
    chassis_number = fields.Char(string='Chassis Number (Asset)')
    engine_number = fields.Char(string='Engine Number')

    lot_id = fields.Many2one(
        'stock.lot',
        string='Fleet Number',
        index='btree_not_null',
        ondelete='restrict',
        copy=False,
        tracking=True,
        domain="[('product_id.is_vehicle', '=', True), ('fleet_vehicle_ids', '=', False), "
               "('company_id', 'in', [company_id, False])]",
        help='Serial Number (stock.lot) of this unit: the link between Inventory and Fleet.',
    )
    fleet_vehicle_lot_id = fields.Many2one(
        'stock.lot',
        string='Serial Number',
        related='lot_id',
        help='Kept for backward compatibility; use Fleet Number (lot_id).',
    )
    fleet_number_pending = fields.Boolean(
        string='Fleet Number Not Linked',
        compute='_compute_fleet_number_pending',
        store=True,
        help='The vehicle has a Fleet Number (Asset Number) but no lot of that '
             'name exists in its company yet. It is linked automatically as soon '
             'as that lot is created.',
    )
    fleet_number_locked = fields.Boolean(compute='_compute_fleet_number_locked')

    _lot_id_uniq = models.Constraint(
        'unique (lot_id)',
        'This Fleet Number is already linked to another vehicle.',
    )

    @api.depends('asset_number', 'lot_id')
    def _compute_fleet_number_pending(self):
        for vehicle in self:
            vehicle.fleet_number_pending = bool(vehicle.asset_number and not vehicle.lot_id)

    @api.depends_context('uid')
    def _compute_fleet_number_locked(self):
        """A saved link is locked; only a system administrator may correct it."""
        is_admin = self.env.user.has_group('base.group_system')
        for vehicle in self:
            vehicle.fleet_number_locked = bool(vehicle._origin.lot_id) and not is_admin

    @api.constrains('lot_id', 'company_id')
    def _check_fleet_number_lot(self):
        for vehicle in self.filtered('lot_id'):
            lot = vehicle.lot_id.sudo()
            if not lot.product_id.is_vehicle:
                raise ValidationError(_(
                    "Fleet Number %(lot)s belongs to %(product)s, which is not a fleet product.",
                    lot=lot.name, product=lot.product_id.display_name,
                ))
            if lot.company_id and vehicle.company_id and lot.company_id != vehicle.company_id:
                raise ValidationError(_(
                    "Fleet Number %(lot)s belongs to company %(lot_company)s, "
                    "but vehicle %(vehicle)s is in company %(company)s.",
                    lot=lot.name, lot_company=lot.company_id.name,
                    vehicle=vehicle.display_name, company=vehicle.company_id.name,
                ))

    @api.constrains('asset_number', 'company_id')
    def _check_unique_asset_number(self):
        """One Fleet Number, one vehicle, per company — linked or still waiting."""
        Vehicle = self.sudo().with_context(active_test=False)
        for vehicle in self.filtered('asset_number'):
            if Vehicle.search_count([
                ('id', '!=', vehicle.id),
                ('asset_number', '=', vehicle.asset_number),
                ('company_id', '=', vehicle.company_id.id),
            ], limit=1):
                raise ValidationError(_(
                    "Fleet Number %(number)s is already used by another vehicle of company %(company)s.",
                    number=vehicle.asset_number,
                    company=vehicle.company_id.display_name or _('(no company)'),
                ))

    # ------------------------------------------------------------------
    # Fleet <-> Lot link (field rules: stock_lot.FLEET_LOT_FIELDS)
    # ------------------------------------------------------------------
    def _find_lot_for_fleet_number(self):
        """The lot this vehicle's Asset Number designates, or an empty recordset.

        Same name, a fleet product, the vehicle's company (or a lot without
        company), and not linked to another vehicle yet. Never guesses: with
        several candidates nothing is returned and the reason is logged.
        """
        self.ensure_one()
        Lot = self.env['stock.lot'].sudo()
        if not self.asset_number:
            return Lot
        domain = [
            ('name', '=', self.asset_number),
            ('product_id.is_vehicle', '=', True),
            ('fleet_vehicle_ids', '=', False),
        ]
        if self.company_id:
            domain.append(('company_id', 'in', [self.company_id.id, False]))
        lots = Lot.search(domain)
        if len(lots) > 1:
            self.message_post(body=_(
                'Fleet Number %s not linked: several lots carry that name. '
                'Pick the right one in the Fleet Number field.',
                self.asset_number,
            ))
            return Lot
        return lots

    def _prepare_lot_vals(self, fleet_fields=None):
        """stock.lot values mirroring ``fleet_fields`` of this vehicle.

        With ``fleet_fields`` omitted (linking) every mapped field is taken, but
        only when set on the vehicle, so a field it lacks never wipes the lot's.
        A year/colour without master record on the lot side is skipped rather
        than cleared.
        """
        self.ensure_one()
        Lot = self.env['stock.lot']
        vals = {}
        for fleet_field, lot_field, kind, _mode in Lot._fleet_lot_fields():
            if fleet_fields is not None and fleet_field not in fleet_fields:
                continue
            value = Lot._fleet_value_to_lot(self, fleet_field, kind)
            if not value and (fleet_fields is None or self[fleet_field]):
                continue
            vals[lot_field] = value
        return vals

    def _merge_with_linked_lot(self):
        """Align a vehicle with its Fleet Number right after they are linked.

        The vehicle has priority: its values overwrite the lot's. Fields the
        vehicle still lacks are completed from the lot — except the analytic
        account, which only ever flows from the vehicle.
        """
        sync = {FLEET_LOT_SYNC: True}
        complete_from_lot = {
            lot_field
            for _f, lot_field, _k, _m in self.env['stock.lot']._fleet_lot_fields()
            if lot_field != 'analytic_account_id'
        }
        for vehicle in self.filtered('lot_id'):
            lot = vehicle.lot_id.sudo()
            fleet_vals = lot._prepare_fleet_vals(complete_from_lot, only_empty_on=vehicle)
            lot_vals = {
                lot_field: value
                for lot_field, value in vehicle._prepare_lot_vals().items()
                if (lot[lot_field].id if isinstance(lot[lot_field], models.BaseModel) else lot[lot_field]) != value
            }
            if lot_vals:
                lot.with_context(**sync).write(lot_vals)
            if fleet_vals:
                vehicle.with_context(**sync).write(fleet_vals)

    def _link_lot_from_asset_number(self):
        """Link vehicles waiting for their Fleet Number to the lot of that name, if any."""
        linked = self.browse()
        for vehicle in self.filtered(lambda v: v.asset_number and not v.lot_id):
            lot = vehicle._find_lot_for_fleet_number()
            if lot:
                vehicle.with_context(**{FLEET_LOT_SYNC: True}).write({'lot_id': lot.id})
                linked |= vehicle
        linked._merge_with_linked_lot()

    @api.model_create_multi
    def create(self, vals_list):
        Lot = self.env['stock.lot'].sudo()
        for vals in vals_list:
            if vals.get('lot_id'):
                vals['asset_number'] = Lot.browse(vals['lot_id']).name
        records = super().create(vals_list)
        if self.env.context.get(FLEET_LOT_SYNC):
            return records
        records.filtered('lot_id')._merge_with_linked_lot()
        records.filtered(lambda r: not r.lot_id)._link_lot_from_asset_number()
        return records

    def write(self, vals):
        syncing = self.env.context.get(FLEET_LOT_SYNC)
        if 'lot_id' in vals:
            if not syncing and not self.env.su and not self.env.user.has_group('base.group_system'):
                for vehicle in self.filtered('lot_id'):
                    if vehicle.lot_id.id != vals['lot_id']:
                        raise UserError(_(
                            "Vehicle %(vehicle)s is already linked to Fleet Number %(lot)s. "
                            "Only an administrator can change it.",
                            vehicle=vehicle.display_name, lot=vehicle.lot_id.name,
                        ))
            if vals['lot_id']:
                vals = dict(vals, asset_number=self.env['stock.lot'].sudo().browse(vals['lot_id']).name)
        elif 'asset_number' in vals and not syncing:
            for vehicle in self.filtered('lot_id'):
                if vehicle.lot_id.name != vals['asset_number']:
                    raise UserError(_(
                        "Asset Number of %(vehicle)s follows its Fleet Number %(lot)s and cannot be changed.",
                        vehicle=vehicle.display_name, lot=vehicle.lot_id.name,
                    ))

        previous_lots = {vehicle.id: vehicle.lot_id for vehicle in self} if 'lot_id' in vals else {}
        res = super().write(vals)
        if syncing:
            return res

        newly_linked = self.filtered(lambda v: v.lot_id and v.id in previous_lots and previous_lots[v.id] != v.lot_id)
        newly_linked._merge_with_linked_lot()
        if 'asset_number' in vals and 'lot_id' not in vals:
            self._link_lot_from_asset_number()

        mapped = {fleet_field for fleet_field, _l, _k, _m in self.env['stock.lot']._fleet_lot_fields()}
        changed = mapped & vals.keys()
        if changed:
            for vehicle in (self - newly_linked).filtered('lot_id'):
                lot_vals = vehicle._prepare_lot_vals(changed)
                if lot_vals:
                    vehicle.lot_id.sudo().with_context(**{FLEET_LOT_SYNC: True}).write(lot_vals)
        return res
