from odoo import api, fields, models, _
from odoo.exceptions import UserError


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    rental_type = fields.Selection([
        ('short_term', 'Short-Term'),
        ('long_term', 'Long-Term')
    ], string='Rental Type', tracking=True)

    is_asset_registered = fields.Boolean(string="Asset Registered", copy=False)

    def button_validate(self):
        """Override Validate: validasi mandatory fields per unit (move_line level)."""
        for picking in self:
            if picking.picking_type_code != 'incoming':
                continue

            missing = []

            if not picking.rental_type:
                missing.append('Rental Type (header GR)')

            for move in picking.move_ids:
                if move.product_id.tracking != 'serial':
                    continue

                is_vehicle = move.product_id.is_vehicle
                product_name = move.product_id.display_name

                if not move.move_line_ids:
                    missing.append(
                        'Detail Operations (produk: %s) — klik tombol Detail untuk mengisi data unit'
                        % product_name
                    )
                    continue

                if move.quantity > move.product_uom_qty:
                    missing.append(
                        'Kuantitas Done (%s) melebihi Demand (%s) untuk produk %s'
                        % (move.quantity, move.product_uom_qty, product_name)
                    )

                for idx, line in enumerate(move.move_line_ids, start=1):
                    unit_label = '%s (unit %d)' % (product_name, idx)

                    if not line.lot_id and not (line.lot_name or '').strip():
                        missing.append('Serial Number — %s' % unit_label)

                    if is_vehicle:
                        if not (line.initial_license_plate or '').strip():
                            missing.append('Initial License Plate — %s' % unit_label)
                        if not (line.chassis_number or '').strip():
                            missing.append('Chassis Number — %s' % unit_label)
                        if not (line.engine_number or '').strip():
                            missing.append('Engine Number — %s' % unit_label)

            if missing:
                raise UserError(
                    _('Unable to validate GR. Please fill in the following fields:\n- %s')
                    % '\n- '.join(missing)
                )

        return super().button_validate()

    def _default_fleet_vehicle_state_for_gr(self):
        """Prefer is_first_destination; else Non-Leased; else standard Fleet Registered; else any state."""
        VehicleState = self.env['fleet.vehicle.state']
        state = VehicleState.search([('is_first_destination', '=', True)], limit=1)
        if not state:
            state = VehicleState.search([('name', '=', 'Non-Leased')], limit=1)
        if state:
            return state.id
        ref = self.env.ref('fleet.fleet_vehicle_state_registered', raise_if_not_found=False)
        if ref:
            return ref.id
        fallback = VehicleState.search([], limit=1, order='sequence, id')
        return fallback.id if fallback else False

    def _fleet_substatus_from_rental_type(self):
        """Map GR rental type to seeded vehicle.substatus records (by module XML id)."""
        self.ensure_one()
        if not self.rental_type:
            return self.env['vehicle.substatus']
        xid_by_rental = {
            'short_term': 'x_stock_asset_receipt.vehicle_substatus_short_term',
            'long_term': 'x_stock_asset_receipt.vehicle_substatus_long_term',
        }
        xid = xid_by_rental.get(self.rental_type)
        if not xid:
            return self.env['vehicle.substatus']
        sub = self.env.ref(xid, raise_if_not_found=False)
        return sub if sub else self.env['vehicle.substatus']

    def action_register_asset_detail(self):
        """
        Buat fleet.vehicle untuk setiap unit (move_line dengan lot_id),
        lalu buka list view dari semua kendaraan yang dibuat.
        """
        self.ensure_one()

        default_state_id = self._default_fleet_vehicle_state_for_gr()

        vehicle_ids = []

        for line in self.move_line_ids.filtered(lambda ml: ml.lot_id):
            existing = self.env['fleet.vehicle'].search(
                [('asset_number', '=', line.lot_id.name)], limit=1
            )
            if existing:
                vehicle_ids.append(existing.id)
                continue

            product = line.product_id
            model = self.env['fleet.vehicle.model'].search([('name', '=', product.name)], limit=1)
            if not model:
                brand = self.env['fleet.vehicle.model.brand'].search([('name', '=', 'Other')], limit=1)
                if not brand:
                    brand = self.env['fleet.vehicle.model.brand'].create({'name': 'Other'})
                
                model = self.env['fleet.vehicle.model'].create({
                    'name': product.name,
                    'brand_id': brand.id,
                })

            fleet_sub = self._fleet_substatus_from_rental_type()
            vehicle_vals = {
                'model_id': model.id,
                'asset_number': line.lot_id.name,
                'chassis_number': line.chassis_number or line.lot_id.chassis_number or '',
                'engine_number': line.engine_number or line.lot_id.engine_number or '',
                'initial_license_plate': line.initial_license_plate or line.lot_id.initial_license_plate or '',
                'fleet_sub_status_id': fleet_sub.id if fleet_sub else False,
                'state_id': default_state_id,
                'model_year': line.vehicle_year_id.name if line.vehicle_year_id else '',
                'color': line.vehicle_color_id.name if line.vehicle_color_id else '',
            }
            vehicle = self.env['fleet.vehicle'].create(vehicle_vals)
            vehicle_ids.append(vehicle.id)

        self.is_asset_registered = True

        if not vehicle_ids:
            raise UserError(
                _('No serial numbers found. Please generate Serial Numbers for each unit '
                  'in the Detailed Operations before registering.')
            )

        if len(vehicle_ids) == 1:
            return {
                'name': _('Fleet Registration'),
                'type': 'ir.actions.act_window',
                'res_model': 'fleet.vehicle',
                'view_mode': 'form',
                'res_id': vehicle_ids[0],
                'target': 'current',
                'context': dict(self.env.context, active_id=vehicle_ids[0], active_ids=[vehicle_ids[0]]),
            }

        return {
            'name': _('Fleet Registration'),
            'type': 'ir.actions.act_window',
            'res_model': 'fleet.vehicle',
            'view_mode': 'list,form',
            'domain': [('id', 'in', vehicle_ids)],
            'target': 'current',
            'context': dict(self.env.context, active_id=False, active_ids=vehicle_ids),
        }
