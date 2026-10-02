from odoo import api, fields, models, _
from odoo.exceptions import UserError


class StockMove(models.Model):
    _inherit = 'stock.move'

    is_replace = fields.Boolean(string='Replace...')

    initial_license_plate = fields.Text(
        string='Initial License Plate',
        compute='_compute_vehicle_fields',
        store=False,
        readonly=True,
    )
    chassis_number = fields.Text(
        string='Chassis Number',
        compute='_compute_vehicle_fields',
        store=False,
        readonly=True,
    )
    engine_number = fields.Text(
        string='Engine Number',
        compute='_compute_vehicle_fields',
        store=False,
        readonly=True,
    )
    vehicle_model = fields.Text(
        string='Model',
        compute='_compute_vehicle_fields',
        store=False,
        readonly=True,
    )
    vehicle_year = fields.Text(
        string='Tahun',
        compute='_compute_vehicle_fields',
        store=False,
        readonly=True,
    )
    vehicle_color = fields.Text(
        string='Warna',
        compute='_compute_vehicle_fields',
        store=False,
        readonly=True,
    )

    display_license_plate = fields.Html(
        string='Initial License Plate (Badges)',
        compute='_compute_vehicle_fields',
        store=False,
        readonly=True,
        sanitize=False,
    )
    display_chassis_number = fields.Html(
        string='Chassis Number (Badges)',
        compute='_compute_vehicle_fields',
        store=False,
        readonly=True,
        sanitize=False,
    )
    display_engine_number = fields.Html(
        string='Engine Number (Badges)',
        compute='_compute_vehicle_fields',
        store=False,
        readonly=True,
        sanitize=False,
    )
    display_vehicle_model = fields.Html(
        string='Model (Badges)',
        compute='_compute_vehicle_fields',
        store=False,
        readonly=True,
        sanitize=False,
    )
    display_vehicle_year = fields.Html(
        string='Tahun (Badges)',
        compute='_compute_vehicle_fields',
        store=False,
        readonly=True,
        sanitize=False,
    )
    display_vehicle_color = fields.Html(
        string='Warna (Badges)',
        compute='_compute_vehicle_fields',
        store=False,
        readonly=True,
        sanitize=False,
    )

    @api.depends('move_line_ids.initial_license_plate',
                 'move_line_ids.chassis_number',
                 'move_line_ids.engine_number',
                 'move_line_ids.vehicle_model_id',
                 'move_line_ids.vehicle_year_id',
                 'move_line_ids.vehicle_color_id')
    def _compute_vehicle_fields(self):
        for move in self:
            plates = [line.initial_license_plate for line in move.move_line_ids if line.initial_license_plate]
            chassis = [line.chassis_number for line in move.move_line_ids if line.chassis_number]
            engines = [line.engine_number for line in move.move_line_ids if line.engine_number]
            vehicle_models = [line.vehicle_model_id.name for line in move.move_line_ids if line.vehicle_model_id]
            years = [line.vehicle_year_id.name for line in move.move_line_ids if line.vehicle_year_id]
            colors = [line.vehicle_color_id.name for line in move.move_line_ids if line.vehicle_color_id]
            
            def make_badges(items, bg_class):
                if not items:
                    return False
                badges = [f'<div style="margin-bottom: 2px;"><span class="badge rounded-pill {bg_class}" style="font-size: 0.85em;">{item}</span></div>' for item in items]
                return '<div class="d-flex flex-column align-items-start">' + ''.join(badges) + '</div>'
            
            move.display_license_plate = make_badges(plates, 'text-bg-primary')
            move.display_chassis_number = make_badges(chassis, 'text-bg-primary')
            move.display_engine_number = make_badges(engines, 'text-bg-primary')
            move.display_vehicle_model = make_badges(vehicle_models, 'text-bg-primary')
            move.display_vehicle_year = make_badges(years, 'text-bg-primary')
            move.display_vehicle_color = make_badges(colors, 'text-bg-primary')

            move.initial_license_plate = '\n'.join(plates) if plates else False
            move.chassis_number = '\n'.join(chassis) if chassis else False
            move.engine_number = '\n'.join(engines) if engines else False
            move.vehicle_model = '\n'.join(vehicle_models) if vehicle_models else False
            move.vehicle_year = '\n'.join(years) if years else False
            move.vehicle_color = '\n'.join(colors) if colors else False

    x_asset_analytic_distribution = fields.Json(
        string='Asset Analytic Distribution',
        copy=False,
        help='Filled from the serial/lot analytic account on stock move lines.',
    )

    analytic_account_domain_ids = fields.Many2many(
        'account.analytic.account',
        string='Allowed Analytic Accounts',
        compute='_compute_analytic_account_domain_ids',
        store=False,
    )

    @api.depends('product_id', 'product_id.is_vehicle')
    def _compute_analytic_account_domain_ids(self):
        """Allowed analytic accounts: those of the vehicles registered for this product.
        Used as domain restriction for the analytic_distribution widget in picking views.
        """
        for move in self:
            if move.product_id and move.product_id.is_vehicle:
                vehicles = self.env['fleet.vehicle'].search([
                    ('lot_id.product_id', '=', move.product_id.id),
                    ('analytic_account_id', '!=', False),
                ])
                move.analytic_account_domain_ids = [(6, 0, vehicles.analytic_account_id.ids)]
            else:
                move.analytic_account_domain_ids = [(5, 0, 0)]

    is_po_fleet_receipt = fields.Boolean(
        string='PO Fleet Receipt',
        compute='_compute_is_po_fleet_receipt',
        store=False,
        help="Receipt line of a fleet product coming from a Purchase Order. "
             "Such a unit gets its own analytic account when it is registered as "
             "a vehicle on Validate (_ensure_fleet_analytic_account), so the "
             "analytic input is hidden on the goods receipt.",
    )

    @api.depends('picking_code', 'product_id.is_vehicle',
                 'purchase_line_id', 'picking_id.purchase_id')
    def _compute_is_po_fleet_receipt(self):
        """Receipt + fleet product + purchase origin — all three, or nothing hides.

        The purchase link is read from the move first: a backorder keeps its
        ``purchase_line_id``, and ``picking.purchase_id`` is itself related to
        ``move_ids.purchase_line_id.order_id``, so it also covers a line added by
        hand onto a receipt that a Purchase Order created.
        """
        for move in self:
            move.is_po_fleet_receipt = bool(
                move.picking_code == 'incoming'
                and move.product_id.is_vehicle
                and (move.purchase_line_id or move.picking_id.purchase_id)
            )

    def _get_analytic_distribution(self):
        try:
            res = super()._get_analytic_distribution()
        except AttributeError:
            res = {}
        custom = self.x_asset_analytic_distribution
        if not custom:
            return res if res else {}
        merged = dict(res or {})
        for key, pct in custom.items():
            merged[str(key)] = float(pct)
        return merged

    def _set_asset_analytic_distribution(self, analytic_account):
        self.ensure_one()
        if not analytic_account:
            return
        distribution = {str(analytic_account.id): 100}
        vals = {}
        if self.x_asset_analytic_distribution != distribution:
            vals['x_asset_analytic_distribution'] = distribution
        if 'x_spk_analytic_distribution' in self._fields and self.x_spk_analytic_distribution != distribution:
            vals['x_spk_analytic_distribution'] = distribution
        if not vals:
            return
        if not self.ids:
            self.update(vals)
        else:
            self.write(vals)

    serial_generated = fields.Boolean(
        string='Serial Generated',
        compute='_compute_serial_generated',
        store=False,
    )

    @api.depends('move_line_ids.lot_id', 'lot_ids')
    def _compute_serial_generated(self):
        for move in self:
            move.serial_generated = bool(
                move.move_line_ids.filtered(lambda l: l.lot_id) or move.lot_ids
            )

    @api.constrains('move_line_ids')
    def _check_single_serial_per_asset(self):
        """Pastikan qty tiap move line tidak melebihi 1 untuk produk serial."""
        for move in self:
            if (move.picking_id.picking_type_code == 'incoming'
                    and move.product_id.tracking == 'serial'):
                for line in move.move_line_ids:
                    if line.quantity and line.quantity > 1.0:
                        raise UserError(
                            _('The quantity for serial-tracked assets must be '
                              'exactly 1.0 (product: %s).')
                            % move.product_id.display_name
                        )

    def action_mass_generate_fn(self):
        for move in self:
            if move.product_id.tracking != 'serial':
                continue
            move.move_line_ids.filtered(lambda line: not line.lot_id)._generate_fleet_number()
        return True

    # ------------------------------------------------------------------
    # Fleet units received from a Purchase Order: one line per unit, qty 0
    # ------------------------------------------------------------------
    # Odoo pre-fills a receipt with its whole demand. For fleet units bought on a
    # PO every unit gets its own detail line from the start, but at quantity 0:
    # the user generates the Fleet Numbers, then sets quantity 1 on the units
    # actually delivered. The lines left at 0 — Fleet Number and unit data
    # included — move on to the backorder instead of being thrown away.

    def _is_fleet_unit_receipt(self):
        self.ensure_one()
        return (
            self.is_po_fleet_receipt
            and self.product_id.tracking == 'serial'
            and self._should_bypass_reservation()
        )

    def _fleet_unit_count(self):
        """Number of units (detail lines) the move should hold."""
        self.ensure_one()
        return int(self.product_qty)

    def _sync_fleet_unit_lines(self):
        """One detail line per unit of demand: add the missing ones at quantity 0,
        drop the surplus left by a lowered demand (unreceived lines without a Fleet
        Number first)."""
        vals_list = []
        for move in self:
            lines = move.move_line_ids.filtered(lambda ml: ml.state not in ('done', 'cancel'))
            missing = move._fleet_unit_count() - len(lines)
            if missing > 0:
                vals_list += [move._prepare_move_line_vals() for _i in range(missing)]
            elif missing < 0:
                spare = lines.filtered(lambda ml: move.product_uom.is_zero(ml.quantity))
                spare = spare.sorted(lambda ml: (bool(ml.lot_id), -ml.id))
                spare[:-missing].unlink()
        if vals_list:
            self.env['stock.move.line'].create(vals_list)._apply_putaway_strategy()

    def _action_assign(self, force_qty=False):
        units = self.filtered(
            lambda m: m.state in ('confirmed', 'waiting', 'partially_available')
            and m._is_fleet_unit_receipt()
        )
        res = super(StockMove, self - units)._action_assign(force_qty=force_qty)
        if units:
            units._sync_fleet_unit_lines()
            units.write({'state': 'assigned'})
        return res

    def _recompute_state(self):
        """A fleet unit receipt with all its detail lines is ready, whatever the
        quantities typed so far (core would call it Waiting at quantity 0)."""
        res = super()._recompute_state()
        if self.env.context.get('preserve_state'):
            return res
        ready = self.filtered(
            lambda m: m.state in ('confirmed', 'partially_available')
            and m._is_fleet_unit_receipt()
            and len(m.move_line_ids) >= m._fleet_unit_count()
        )
        if ready:
            ready.state = 'assigned'
        return res

    def _set_quantity(self):
        """Quantity typed on the Operations tab: receive that many units.

        Units already set to 1 in the detail stay received; more are taken from
        the remaining lines in order, or released from the last ones. Detail lines
        are never deleted, so their Fleet Number survives.
        """
        units = self.filtered(lambda m: m.state not in ('done', 'cancel') and m._is_fleet_unit_receipt())
        res = super(StockMove, self - units)._set_quantity()
        for move in units:
            wanted = move.quantity
            if wanted < 0 or not float(wanted).is_integer():
                raise UserError(_('Quantity of %s must be a whole number of units.', move.product_id.display_name))
            lines = move.move_line_ids.filtered(lambda ml: ml.state not in ('done', 'cancel')).sorted('id')
            received = lines.filtered(lambda ml: not move.product_uom.is_zero(ml.quantity))
            if wanted > len(lines):
                raise UserError(_(
                    'Only %(count)s unit line(s) exist for %(product)s: '
                    'a Goods Receipt cannot receive more units than ordered.',
                    count=len(lines), product=move.product_id.display_name,
                ))
            extra = int(wanted) - len(received)
            if extra > 0:
                (lines - received)[:extra].write({'quantity': 1.0})
            elif extra < 0:
                received.sorted('id', reverse=True)[:-extra].write({'quantity': 0.0})
        return res

    def _action_done(self, cancel_backorder=False):
        if not cancel_backorder:
            # Core unlinks the unpicked lines of a picked move before splitting it;
            # keep the unreceived unit lines alive for _create_backorder().
            waiting = self.filtered(
                lambda m: m.state not in ('done', 'cancel') and m.picked and m._is_fleet_unit_receipt()
            ).move_line_ids.filtered(lambda ml: not ml.picked and ml.product_uom_id.is_zero(ml.quantity))
            waiting.picked = True
        return super()._action_done(cancel_backorder=cancel_backorder)

    def _create_backorder(self):
        """Hand the unreceived unit lines over to the backorder move, Fleet Number
        and unit data included, instead of letting core drop them and start the
        backorder with blank lines."""
        backorder_moves = super()._create_backorder()
        for move in self.filtered(lambda m: m._is_fleet_unit_receipt()):
            waiting = move.move_line_ids.filtered(lambda ml: ml.product_uom_id.is_zero(ml.quantity))
            target = backorder_moves.filtered(
                lambda bo: bo.product_id == move.product_id
                and bo.purchase_line_id == move.purchase_line_id
            )[:1]
            if waiting and target:
                waiting.write({'move_id': target.id, 'picked': False})
                # Confirming the backorder move already gave it blank unit lines.
                target._sync_fleet_unit_lines()
        return backorder_moves
