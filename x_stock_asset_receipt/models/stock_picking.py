from odoo import api, fields, models, _
from odoo.exceptions import UserError


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    rental_type = fields.Selection([
        ('short_term', 'Short-Term'),
        ('long_term', 'Long-Term')
    ], string='Rental Type', tracking=True)

    def button_validate(self):
        """Override Validate: validasi mandatory fields per unit (move_line level)."""
        for picking in self:
            if picking.picking_type_code != 'incoming':
                continue

            missing = []

            # 1. Rental Type wajib diisi di header
            if not picking.rental_type:
                missing.append('Rental Type (header GR)')

            # 2. Validasi per move → per move_line (satu unit fisik)
            for move in picking.move_ids:
                if move.product_id.tracking != 'serial':
                    continue

                is_vehicle = move.product_id.is_vehicle
                product_name = move.product_id.display_name

                # Pastikan ada move_line (unit detail sudah diisi)
                if not move.move_line_ids:
                    missing.append(
                        'Detail Operations (produk: %s) — klik tombol Detail untuk mengisi data unit'
                        % product_name
                    )
                    continue

                # Cek Kuantitas vs Demand
                if move.quantity > move.product_uom_qty:
                    missing.append(
                        'Kuantitas Done (%s) melebihi Demand (%s) untuk produk %s'
                        % (move.quantity, move.product_uom_qty, product_name)
                    )

                for idx, line in enumerate(move.move_line_ids, start=1):
                    unit_label = '%s (unit %d)' % (product_name, idx)

                    # Serial Number wajib untuk semua produk serial
                    if not line.lot_id and not (line.lot_name or '').strip():
                        missing.append('Serial Number — %s' % unit_label)

                    # Field kendaraan hanya wajib jika is_vehicle = True
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

    def action_register_asset_detail(self):
        """
        Buat fleet.vehicle untuk setiap unit (move_line dengan lot_id),
        lalu buka list view dari semua kendaraan yang dibuat.
        """
        self.ensure_one()

        default_state_id = self._default_fleet_vehicle_state_for_gr()

        vehicle_ids = []

        for line in self.move_line_ids.filtered(lambda ml: ml.lot_id):
            # Cek apakah vehicle dengan asset_number ini sudah ada
            existing = self.env['fleet.vehicle'].search(
                [('asset_number', '=', line.lot_id.name)], limit=1
            )
            if existing:
                vehicle_ids.append(existing.id)
                continue

            # Cari atau buat Fleet Model berdasarkan nama produk
            product = line.product_id
            model = self.env['fleet.vehicle.model'].search([('name', '=', product.name)], limit=1)
            if not model:
                # Cari brand 'Other' atau buat jika belum ada
                brand = self.env['fleet.vehicle.model.brand'].search([('name', '=', 'Other')], limit=1)
                if not brand:
                    brand = self.env['fleet.vehicle.model.brand'].create({'name': 'Other'})
                
                model = self.env['fleet.vehicle.model'].create({
                    'name': product.name,
                    'brand_id': brand.id,
                })

            # Buat fleet.vehicle baru
            vehicle_vals = {
                'model_id': model.id,
                'asset_number': line.lot_id.name,
                'chassis_number': line.chassis_number or line.lot_id.chassis_number or '',
                'engine_number': line.engine_number or line.lot_id.engine_number or '',
                'initial_license_plate': line.initial_license_plate or line.lot_id.initial_license_plate or '',
                'fleet_sub_status': self.rental_type or False,
                'state_id': default_state_id,
            }
            vehicle = self.env['fleet.vehicle'].create(vehicle_vals)
            vehicle_ids.append(vehicle.id)

        if not vehicle_ids:
            raise UserError(
                _('No serial numbers found. Please generate Serial Numbers for each unit '
                  'in the Detailed Operations before registering.')
            )

        # Jika hanya 1 unit, buka form langsung
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

        # Jika > 1 unit, buka list view
        return {
            'name': _('Fleet Registration'),
            'type': 'ir.actions.act_window',
            'res_model': 'fleet.vehicle',
            'view_mode': 'list,form',
            'domain': [('id', 'in', vehicle_ids)],
            'target': 'current',
            'context': dict(self.env.context, active_id=False, active_ids=vehicle_ids),
        }
