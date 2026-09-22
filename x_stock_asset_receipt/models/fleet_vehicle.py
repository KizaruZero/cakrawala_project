from odoo import _, api, models, fields


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
    )
    asset_type = fields.Char(string='Asset Type (Legacy)', help='Kept for Odoo Studio backward compatibility')
    asset_number = fields.Char(string='Asset Number')
    unit_classification = fields.Char(string='Unit Classification')
    assignment_date = fields.Date(string='Assignment Date (Asset)')
    plan_to_disposal = fields.Boolean(string='Plan to Disposal')
    initial_license_plate = fields.Char(string='Initial License Plate')
    chassis_number = fields.Char(string='Chassis Number (Asset)')
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
            vehicle.fleet_vehicle_lot_id = vehicle._matching_lots()[:1]

    def _matching_lots(self):
        """Serial numbers bridged to this vehicle through Fleet Number.

        sudo for the same reason as ``stock.lot._matching_fleet_vehicles``: a
        Fleet user has no access to stock.lot, and without it the sync silently
        did nothing. Company-agnostic on purpose, like the lot side.
        """
        self.ensure_one()
        if not self.asset_number:
            return self.env['stock.lot']
        return self.env['stock.lot'].sudo().search([('name', '=', self.asset_number)])

    def _sync_lots_from_vehicle(self, forced_vehicle_fields=()):
        """Push this vehicle onto its serial number(s), both ways.

        Fields named in ``forced_vehicle_fields`` were just edited here and are
        mirrored verbatim. Everything else in the map is only backfilled, in
        either direction — so editing one field also repairs whatever the two
        sides were still missing, without ever overwriting existing data.
        """
        Lot = self.env['stock.lot']
        forced_lot_fields = {
            lot_field
            for fleet_field, lot_field, _kind in Lot._fleet_sync_fields()
            if fleet_field in forced_vehicle_fields
        }
        for vehicle in self:
            lots = vehicle._matching_lots()
            if not lots:
                continue
            lots._write_lot_from_fleet(forced_lot_fields, fleet=vehicle)
            # Fill in what the vehicle itself is missing (a lot may have been
            # completed before this record existed).
            lots[:1]._write_fleet_from_lot()

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        if self.env.context.get('skip_sync_lot'):
            return records

        sync_map = self.env['stock.lot']._fleet_sync_fields()
        for record, vals in zip(records, vals_list):
            forced = {
                fleet_field
                for fleet_field, _lot_field, _kind in sync_map
                if vals.get(fleet_field)
            }
            record._sync_lots_from_vehicle(forced_vehicle_fields=forced)
        return records

    def write(self, vals):
        res = super().write(vals)
        if self.env.context.get('skip_sync_lot'):
            return res

        sync_map = self.env['stock.lot']._fleet_sync_fields()
        forced = {
            fleet_field
            for fleet_field, _lot_field, _kind in sync_map
            if fleet_field in vals
        }
        if not forced and 'asset_number' not in vals:
            return res

        self._sync_lots_from_vehicle(forced_vehicle_fields=forced)
        return res
