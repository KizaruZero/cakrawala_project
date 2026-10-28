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
                    # an account of another company cannot be read (nor used) here
                    ('analytic_account_id.company_id', 'in', [False, move.company_id.id]),
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
        self._write_fleet_analytic_distribution({str(analytic_account.id): 100})

    def _write_fleet_analytic_distribution(self, distribution):
        """Write one distribution on every analytic field a move carries.

        A move holds its analytic account in up to four fields (shown one from
        x_spk, the hidden one used for the analytic items, the one copied from the
        Sales Order line, the disposal one). They must never disagree: two
        different accounts at 100% each would book 200%.
        """
        self.ensure_one()
        distribution = distribution or False
        vals = {}
        if self.x_asset_analytic_distribution != distribution:
            vals['x_asset_analytic_distribution'] = distribution
        if 'x_spk_analytic_distribution' in self._fields and self.x_spk_analytic_distribution != distribution:
            vals['x_spk_analytic_distribution'] = distribution
        # only a disposal delivery uses this one
        if ('x_disposal_analytic_distribution' in self._fields and self.x_disposal_analytic_distribution
                and self.x_disposal_analytic_distribution != distribution):
            vals['x_disposal_analytic_distribution'] = distribution
        if 'analytic_account_id' in self._fields:
            account_ids = self._analytic_account_ids(distribution)
            account = self.env['account.analytic.account'].browse(account_ids[:1] if len(account_ids) == 1 else [])
            if self.analytic_account_id != account:
                vals['analytic_account_id'] = account.id
        if not vals:
            return
        if not self.ids:
            self.update(vals)
        else:
            self.write(vals)

    @api.model
    def _analytic_account_ids(self, distribution):
        """Account ids of a distribution, in order (a key may hold several: "3,7")."""
        ids = []
        for key in distribution or {}:
            for part in str(key).split(','):
                if part.strip().isdigit() and int(part) not in ids:
                    ids.append(int(part))
        return ids

    @api.model
    def _normalize_analytic_weights(self, weights):
        """{analytic key: weight} -> percentages totalling exactly 100.

        Rounded down to the analytic precision, the remainder handed out one step
        at a time: three units give 33.34 / 33.33 / 33.33, never 99.99.
        """
        weights = {key: weight for key, weight in weights.items() if weight > 0}
        total = sum(weights.values())
        if not total:
            return {}
        digits = self.env['decimal.precision'].precision_get('Percentage Analytic')
        steps = 100 * 10 ** digits
        exact = {key: weight * steps / total for key, weight in weights.items()}
        shares = {key: int(value) for key, value in exact.items()}
        for key in sorted(exact, key=lambda k: exact[k] - shares[k], reverse=True)[:steps - sum(shares.values())]:
            shares[key] += 1
        return {key: round(share / 10 ** digits, digits) for key, share in shares.items()}

    def _is_fleet_delivery_move(self):
        """A fleet unit that is not received here (delivery, internal, return).

        Such a unit is an existing vehicle: its analytic account is the one of
        its Fleet Number, and the two always follow each other.
        """
        self.ensure_one()
        return bool(
            self.product_id.is_vehicle
            and self.product_id.tracking == 'serial'
            and self.picking_code != 'incoming'
        )

    is_fleet_source_locked = fields.Boolean(
        string='Vehicle Fixed by Source',
        compute='_compute_is_fleet_source_locked',
        help='Transfer made for a BASTK, a replacement car or a disposal: its vehicle '
             '(Fleet Number / analytic account) is chosen on that document.',
    )

    @api.depends('picking_id', 'product_id')
    def _compute_is_fleet_source_locked(self):
        for move in self:
            move.is_fleet_source_locked = bool(move._fleet_source_lot())

    def _fleet_source_lot(self):
        """Fleet Number this move must deliver, fixed by its source document."""
        self.ensure_one()
        if not self.picking_id or not self._is_fleet_delivery_move():
            return self.env['stock.lot']
        lot = self.picking_id._fleet_source_lot()
        return lot if lot.product_id == self.product_id else self.env['stock.lot']

    def _check_fleet_source_lot(self, lot):
        """A transfer made for a BASTK / replacement car / disposal moves that vehicle only."""
        for move in self:
            source_lot = move._fleet_source_lot()
            if source_lot and lot and lot != source_lot:
                raise UserError(move._fleet_source_lock_message(lot))

    def _fleet_source_lock_message(self, lots=None):
        self.ensure_one()
        return _(
            "%(picking)s is made for %(source)s: it delivers Fleet Number %(lot)s%(asked)s. "
            "Change the vehicle on %(source)s, not on the transfer.",
            picking=self.picking_id.name, source=self.picking_id._fleet_source_label(),
            lot=self._fleet_source_lot().name,
            asked=_(' (asked: %s)', ', '.join(lots.mapped('name'))) if lots else '',
        )

    def _sync_fleet_analytic_from_lines(self):
        """Analytic of a fleet move = the accounts of the Fleet Numbers it holds.

        A move holding no Fleet Number yet keeps its account: that is the vehicle
        wanted (Sales Order line, BASTK), reserved by ``_action_assign``.
        """
        for move in self:
            if move.state in ('done', 'cancel') or not move._is_fleet_delivery_move():
                continue
            lines = move.move_line_ids.filtered('lot_id')
            if not lines:
                continue
            weights = {}
            for line in lines:
                if line.analytic_account_id:
                    key = str(line.analytic_account_id.id)
                    weights[key] = weights.get(key, 0) + 1
            move._write_fleet_analytic_distribution(self._normalize_analytic_weights(weights))

    def _fleet_wanted_accounts(self):
        """Analytic accounts this move asks for, i.e. the vehicles it must deliver."""
        self.ensure_one()
        Account = self.env['account.analytic.account']
        if 'analytic_account_id' in self._fields and self.analytic_account_id:
            return self.analytic_account_id
        distribution = self.x_asset_analytic_distribution
        if not distribution and 'x_spk_analytic_distribution' in self._fields:
            distribution = self.x_spk_analytic_distribution
        return Account.browse(self._analytic_account_ids(distribution)).exists()

    def _fleet_lot_for_account(self, account):
        """Fleet Number of the vehicle owning ``account`` (same product, company)."""
        self.ensure_one()
        lots = self.env['stock.lot'].search([
            ('product_id', '=', self.product_id.id),
            ('analytic_account_id', '=', account.id),
            ('company_id', 'in', [False, self.company_id.id]),
        ])
        if len(lots) > 1:
            # an account shared by two vehicles (legacy data): take the one in stock here
            available = lots.filtered(self._fleet_available_quant)
            if len(available) == 1:
                lots = available
        return lots

    def _fleet_available_quant(self, lot):
        """Quant of ``lot`` free to be reserved by this move at its source location."""
        self.ensure_one()
        open_allocated = self.env['stock.move.line'].search([
            ('lot_id', '=', lot.id),
            ('move_id.state', 'not in', ('done', 'cancel')),
            ('move_id.picking_code', '=', 'outgoing'),
            ('move_id', '!=', self.id),
        ], limit=1)
        if open_allocated:
            return self.env['stock.quant']

        quants = self.env['stock.quant'].search([
            ('lot_id', '=', lot.id),
            ('location_id', 'child_of', self.location_id.id),
            ('quantity', '>', 0),
        ])
        return quants.filtered(
            lambda q: q.product_uom_id.compare(q.quantity - q.reserved_quantity, 1.0) >= 0
        )[:1]

    def _assign_fleet_lots_from_accounts(self, accounts, strict=True):
        """Reserve, on this move, the Fleet Number of each analytic account.

        Lines already holding one of these Fleet Numbers stay; the other lines
        are moved to the missing Fleet Numbers (Odoo moves the reservation), and
        new lines are added when there are more accounts than lines.

        ``strict`` (user choice): any account that cannot be served raises, and
        a line whose account was removed is released. Otherwise (automatic
        reservation) what cannot be served is returned as messages.
        """
        self.ensure_one()
        problems = []
        lots = self.env['stock.lot']
        for account in accounts:
            lot = self._fleet_lot_for_account(account)
            if len(lot) == 1:
                lots |= lot
            elif not lot:
                problems.append(_('No Fleet Number of %(product)s has the analytic account %(account)s.',
                                  product=self.product_id.display_name, account=account.display_name))
            else:
                problems.append(_('Analytic account %(account)s is used by several Fleet Numbers (%(lots)s): '
                                  'choose the Fleet Number itself.',
                                  account=account.display_name, lots=', '.join(lot.mapped('name'))))
        units = int(self.product_qty)
        if len(lots) > units:
            problems.append(_('%(product)s: %(count)s analytic accounts chosen for %(units)s unit(s).',
                              product=self.product_id.display_name, count=len(lots), units=units))
            lots = self.env['stock.lot']
        if strict and problems:
            raise UserError('\n'.join(problems))
        source_lot = self._fleet_source_lot()
        if source_lot and lots != source_lot:
            message = self._fleet_source_lock_message(lots)
            if strict:
                raise UserError(message)
            return problems + [message]
        return problems + self._assign_fleet_lots(lots, strict=strict)

    def _assign_fleet_lots(self, lots, strict=True):
        """Reserve exactly these Fleet Numbers on this move (see above)."""
        self.ensure_one()
        problems = []
        lines = self.move_line_ids
        kept = lines.filtered(lambda line: line.lot_id in lots)
        free = (lines - kept).sorted('id')
        for lot in lots - kept.lot_id:
            quant = self._fleet_available_quant(lot)
            if not quant:
                problems.append(_('Fleet Number %(lot)s is not available in %(location)s '
                                  '(not in stock there, or already reserved by another transfer).',
                                  lot=lot.name, location=self.location_id.display_name))
                continue
            if free:
                line, free = free[0], free[1:]
                line.write({'quant_id': quant.id})
            else:
                self.env['stock.move.line'].create(
                    self._prepare_move_line_vals(quantity=0.0, reserved_quant=quant))
        if strict:
            if problems:
                raise UserError('\n'.join(problems))
            free.unlink()
        return problems

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

    def _is_fleet_unit_receipt(self):
        """Fleet units bought on a PO, from a vendor or from a company of this
        database (Odoo routes the latter through the inter-company transit
        location). Without an inter-company module nothing is ever shipped into
        transit, so such a receipt brings new units with Fleet Numbers generated
        here, exactly like a vendor receipt. Revisit if inter-company delivery is
        installed: the units would then come with the shipping company's lots.
        """
        self.ensure_one()
        return (
            self.is_po_fleet_receipt
            and self.product_id.tracking == 'serial'
            and (self._should_bypass_reservation() or self.location_id.usage == 'transit')
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
        # Moves that already have allocated fleet units (MTO or MTS chained from GR)
        fleet_allocated_moves = self.filtered(
            lambda m: m.state not in ('done', 'cancel')
            and m.picking_code == 'outgoing'
            and m.product_id.is_vehicle
            and m.move_line_ids.filtered(lambda ml: ml.lot_id)
        )
        for move in fleet_allocated_moves:
            if move.state != 'assigned':
                move.write({'state': 'assigned'})

        remaining_moves = self - fleet_allocated_moves

        units = remaining_moves.filtered(
            lambda m: m.state in ('confirmed', 'waiting', 'partially_available')
            and m._is_fleet_unit_receipt()
        )
        locked = self.env['stock.move']
        for move in remaining_moves.filtered(
            lambda m: m.state in ('confirmed', 'partially_available') and m._is_fleet_delivery_move()
        ):
            source_lot = move._fleet_source_lot()
            if source_lot:
                locked |= move
                problems = move._assign_fleet_lots(source_lot, strict=False)
                if problems and move.picking_id:
                    move.picking_id.message_post(body=_(
                        '%(source)s: %(problems)s Nothing else is reserved: the vehicle is chosen on %(source)s.',
                        source=move.picking_id._fleet_source_label(), problems=' '.join(problems)))
                continue
            accounts = move._fleet_wanted_accounts()
            if accounts:
                locked |= move
                problems = move._assign_fleet_lots_from_accounts(accounts, strict=False)
                if problems and move.picking_id:
                    move.picking_id.message_post(body=_(
                        'The vehicle asked for could not be reserved: %s', ' '.join(problems)))
            else:
                locked |= move
        res = super(StockMove, remaining_moves - units - locked)._action_assign(force_qty=force_qty)
        if units:
            units._sync_fleet_unit_lines()
            units.write({'state': 'assigned'})

        outgoing_fleet_moves = self.filtered(
            lambda m: m.picking_code == 'outgoing' and m.product_id.is_vehicle and m.state not in ('done', 'cancel')
        )
        for move in outgoing_fleet_moves:
            unpicked_lines = move.move_line_ids.filtered(lambda ml: not ml.picked and ml.lot_id)
            if unpicked_lines:
                if hasattr(unpicked_lines, '_sync_vehicle_fields_from_lot'):
                    unpicked_lines._sync_vehicle_fields_from_lot()
                unpicked_lines.with_context(skip_quant_unreserve=True).write({
                    'quantity': 0.0,
                    'picked': False,
                })
            if unpicked_lines and move.state != 'assigned':
                move.write({'state': 'assigned'})

        return res

    def _recompute_state(self):
        """A fleet unit receipt with all its detail lines is ready, whatever the
        quantities typed so far (core would call it Waiting at quantity 0).
        Also preserves assigned state for outgoing moves with allocated fleet units."""
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
        outgoing_ready = self.filtered(
            lambda m: m.state in ('confirmed', 'waiting', 'partially_available')
            and m.picking_code == 'outgoing'
            and m.product_id.is_vehicle
            and m.move_line_ids.filtered(lambda ml: ml.lot_id)
        )
        if outgoing_ready:
            outgoing_ready.state = 'assigned'

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
