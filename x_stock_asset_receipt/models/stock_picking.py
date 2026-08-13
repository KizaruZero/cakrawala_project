from odoo import api, fields, models, _
from odoo.exceptions import UserError


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    rental_type_id = fields.Many2one(
        'vehicle.substatus',
        string='Rental Type',
        domain=[('is_rental_type', '=', True)],
        ondelete='restrict',
        tracking=True,
        help='Sub-status flagged as Rental Type in Master Sub Status. '
             'The value picked here is applied as Fleet Sub-Status when the asset is registered.',
    )

    is_asset_registered = fields.Boolean(
        string="Asset Registered",
        compute='_compute_is_asset_registered',
        store=True,
        copy=False,
    )
    has_vehicle_product = fields.Boolean(
        string="Has Vehicle Product",
        compute='_compute_has_vehicle_product',
    )
    is_from_sales_order = fields.Boolean(
        string="Is From Sales Order",
        compute='_compute_is_from_sales_order',
    )

    def _compute_is_from_sales_order(self):
        for picking in self:
            picking.is_from_sales_order = hasattr(picking, 'sale_id') and bool(picking.sale_id)

    is_bastk_linked = fields.Boolean(
        string="Is BASTK Linked",
        compute='_compute_is_bastk_linked',
    )

    def _compute_is_bastk_linked(self):
        for picking in self:
            picking.is_bastk_linked = hasattr(picking, 'bastk_id') and bool(picking.bastk_id)

    @api.depends(
        'state',
        'picking_type_code',
        'move_line_ids.lot_id',
        'move_ids.product_id.is_vehicle',
    )
    def _compute_is_asset_registered(self):
        FleetVehicle = self.env['fleet.vehicle']
        for picking in self:
            if picking.picking_type_code != 'incoming' or picking.state != 'done':
                picking.is_asset_registered = False
                continue

            lot_lines = picking.move_line_ids.filtered(
                lambda ml: ml.lot_id and ml.product_id.is_vehicle
            )
            if lot_lines:
                all_registered = all(
                    FleetVehicle.search_count([('asset_number', '=', ml.lot_id.name)]) > 0
                    for ml in lot_lines
                )
                picking.is_asset_registered = all_registered
                continue

            picking.is_asset_registered = False

    @api.depends('move_ids.product_id.is_vehicle', 'move_ids.state')
    def _compute_has_vehicle_product(self):
        for picking in self:
            active_moves = picking.move_ids.filtered(
                lambda m: m.state != 'cancel' and m.product_id
            )
            picking.has_vehicle_product = any(
                move.product_id.is_vehicle for move in active_moves
            )

    def button_validate(self):
        """Override Validate: validasi mandatory fields per unit (move_line level)."""
        for picking in self:
            if picking.picking_type_code != 'incoming':
                continue

            missing = []

            # Rental Type hanya relevan kalau ada produk fleet (product.is_vehicle).
            # GR untuk sparepart/jasa tidak perlu diminta mengisi ini.
            if picking.has_vehicle_product and not picking.rental_type_id:
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
        """The GR rental type IS a vehicle.substatus record now — nothing to map."""
        self.ensure_one()
        return self.rental_type_id

    def action_register_asset_detail(self):
        """
        Buat fleet.vehicle untuk setiap unit (move_line dengan lot_id),
        lalu buka list view dari semua kendaraan yang dibuat.
        """
        self.ensure_one()

        default_state_id = self._default_fleet_vehicle_state_for_gr()

        vehicle_ids = []
        vehicle_lines = self.move_line_ids.filtered(
            lambda ml: ml.lot_id and ml.product_id.is_vehicle
        )

        for line in vehicle_lines:
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

            lot_vals = {}
            if line.vehicle_year_id:
                lot_vals['vehicle_year_id'] = line.vehicle_year_id.id
            if line.vehicle_color_id:
                lot_vals['vehicle_color_id'] = line.vehicle_color_id.id
            if lot_vals:
                line.lot_id.with_context(skip_sync_fleet=True).write(lot_vals)

        self._compute_is_asset_registered()

        if not vehicle_ids:
            raise UserError(
                _('No vehicle serial numbers found. Please generate Serial Numbers for each '
                  'vehicle unit in the Detailed Operations before registering.')
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

    def action_mass_generate_fn(self):
        for picking in self:
            picking.move_ids.action_mass_generate_fn()
        return True
