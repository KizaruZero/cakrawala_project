from odoo import Command, api, fields, models, _
from odoo.exceptions import UserError, ValidationError

# Depreciation board entries that close an asset through a refinancing
# transaction (leaseback, sell or dispose).
REFINANCING_MOVE_TYPES = ("sale", "disposal")


class AccountAsset(models.Model):
    _inherit = "account.asset"

    partner_id = fields.Many2one(
        "res.partner",
        string="Partner Link",
        compute="_compute_partner_id",
    )
    incoming_payment_ids = fields.One2many(
        "account.payment",
        "asset_id",
        string="Incoming Payments",
    )
    purchase_order_ids = fields.One2many(
        "purchase.order",
        "asset_id",
        string="Purchase Orders",
    )
    incoming_payment_ref = fields.Many2one(
        "account.payment",
        string="Incoming Payment Reference",
        compute="_compute_incoming_payment_info",
        store=True,
        tracking=True,
    )
    incoming_payment_status = fields.Selection(
        [
            ("draft", "Draft"),
            ("in_process", "In Process"),
            ("paid", "Paid"),
            ("canceled", "Canceled"),
            ("rejected", "Rejected"),
        ],
        string="Incoming Payment Status",
        compute="_compute_incoming_payment_info",
        store=True,
        tracking=True,
    )
    purchase_order_ref = fields.Many2one(
        "purchase.order",
        string="Purchase Order Reference",
        compute="_compute_purchase_order_info",
        store=True,
        tracking=True,
    )
    purchase_order_status = fields.Selection(
        [
            ("draft", "RFQ"),
            ("waiting_approval", "Waiting Approval"),
            ("sent", "RFQ Sent"),
            ("to approve", "To Approve"),
            ("purchase", "Purchase Order"),
            ("done", "Locked"),
            ("cancel", "Cancelled"),
            ("rejected", "Rejected"),
        ],
        string="Purchase Order Status",
        compute="_compute_purchase_order_info",
        store=True,
        tracking=True,
    )
    leaseback_deferred_pl_amount = fields.Monetary(
        string="Deferred Profit/Loss",
        currency_field="currency_id",
        default=0.0,
        readonly=True,
        copy=False,
        tracking=True,
        help="Nilai selisih laba/rugi ditangguhkan dari transaksi leaseback.",
    )
    x_is_refinanced = fields.Boolean(
        string="Refinanced",
        compute="_compute_x_refinancing_info",
        store=True,
        help="Set when the asset went through a refinancing transaction "
        "(leaseback, sell or dispose).",
    )
    x_refinancing_type = fields.Selection(
        [
            ("leaseback", "Leaseback"),
            ("sell", "Sell"),
            ("dispose", "Dispose"),
        ],
        string="Refinancing Type",
        compute="_compute_x_refinancing_info",
        store=True,
    )
    x_refinancing_date = fields.Date(
        string="Refinancing Date",
        compute="_compute_x_refinancing_info",
        store=True,
    )
    x_refinancing_move_id = fields.Many2one(
        "account.move",
        string="Refinancing Entry",
        compute="_compute_x_refinancing_info",
        store=True,
        help="Depreciation board entry that closed the asset through a refinancing.",
    )
    analytic_distribution = fields.Json(
        readonly=True,
        help="Diambil otomatis dari Analytic Account milik vehicle yang dipilih.",
    )
    x_pre_refinancing_move_id = fields.Many2one(
        "account.move",
        string="Last Depreciation Before Refinancing",
        compute="_compute_x_refinancing_info",
        store=True,
        help="Last normal depreciation entry booked before the refinancing entry. "
        "Downstream flows (e.g. fleet disposal) must read the depreciation values "
        "from this entry instead of the latest board entry.",
    )

    @api.depends("vehicle_id.analytic_account_id")
    def _compute_analytic_distribution(self):
        super()._compute_analytic_distribution()
        for rec in self:
            if not rec.vehicle_id:
                # Asset non-fleet: biarkan distribusi yang sudah ada apa adanya,
                # jangan dihapus hanya karena tidak punya vehicle.
                continue
            analytic = rec.vehicle_id.analytic_account_id
            rec.analytic_distribution = (
                {str(analytic.id): 100.0} if analytic else False
            )

    @api.depends("original_move_line_ids.move_id.partner_id")
    def _compute_partner_id(self):
        for rec in self:
            partner = self.env["res.partner"]
            if rec.original_move_line_ids:
                partners = rec.original_move_line_ids.mapped("move_id.partner_id")
                if partners:
                    partner = partners[0]
            rec.partner_id = partner

    @api.depends("incoming_payment_ids.name", "incoming_payment_ids.state")
    def _compute_incoming_payment_info(self):
        for rec in self:
            payment = rec.incoming_payment_ids.sorted(key="id", reverse=True)[:1]
            if payment:
                rec.incoming_payment_ref = payment.id
                rec.incoming_payment_status = payment.state
            else:
                rec.incoming_payment_ref = False
                rec.incoming_payment_status = False

    @api.depends("purchase_order_ids.name", "purchase_order_ids.state")
    def _compute_purchase_order_info(self):
        for rec in self:
            po = rec.purchase_order_ids.sorted(key="id", reverse=True)[:1]
            if po:
                rec.purchase_order_ref = po.id
                rec.purchase_order_status = po.state
            else:
                rec.purchase_order_ref = False
                rec.purchase_order_status = False

    def action_create_incoming_payment(self):
        self.ensure_one()
        if self.incoming_payment_ref:
            raise UserError(_("Incoming Payment sudah dibuat untuk aset ini."))

        action = self.env["ir.actions.actions"]._for_xml_id("account.action_account_payments")
        action.update({
            "views": [(self.env.ref("account.view_account_payment_form").id, "form")],
            "view_mode": "form",
            "target": "current",
            "context": {
                **self.env.context,
                "default_payment_type": "inbound",
                "default_partner_type": "customer",
                "default_partner_id": self.partner_id.id if self.partner_id else False,
                "default_asset_id": self.id,
            },
        })
        return action

    def _get_purchase_order_redirect_context(self):
        self.ensure_one()
        context = {
            **self.env.context,
            "default_origin": self.name,
            "default_partner_ref": self.name,
            "default_asset_id": self.id,
        }
        if self.partner_id:
            context["default_partner_id"] = self.partner_id.id

        po_model = self.env["purchase.order"]
        if "purchase_order_type_master_id" in po_model._fields:
            po_type = (
                self.env["purchase.order.type.master"].search([("state", "=", "active")], limit=1)
                or self.env["purchase.order.type.master"].search([], limit=1)
            )
            if po_type:
                context["default_purchase_order_type_master_id"] = po_type.id
        if "department_id" in po_model._fields:
            department = self.env["hr.department"].search([], limit=1)
            if department:
                context["default_department_id"] = department.id
        return context

    def action_create_purchase_order(self):
        self.ensure_one()
        if self.purchase_order_ref:
            raise UserError(_("Purchase Order sudah dibuat untuk aset ini."))

        action = self.env["ir.actions.actions"]._for_xml_id("purchase.purchase_form_action")
        action.update({
            "views": [(self.env.ref("purchase.purchase_order_form").id, "form")],
            "view_mode": "form",
            "target": "current",
            "context": self._get_purchase_order_redirect_context(),
        })
        return action

    x_is_fleet = fields.Boolean(
        string="Is Fleet",
        compute="_compute_x_is_fleet",
        store=True,
        readonly=False,
        help="Turn this on for an asset model to declare that its assets belong "
        "to a vehicle. Assets created from such a model require a Vehicle, and "
        "their analytic distribution follows that vehicle.",
    )

    @api.depends("model_id")
    def _compute_x_is_fleet(self):
        for asset in self:
            asset.x_is_fleet = asset.model_id.x_is_fleet

    @api.onchange("vehicle_id")
    def _onchange_vehicle_id_analytic_distribution(self):
        self._apply_vehicle_analytic_distribution()

    def _apply_vehicle_analytic_distribution(self):
        """The analytic of a fleet asset is the analytic of its vehicle."""
        if "vehicle_id" not in self._fields:
            return
        for asset in self:
            vehicle = asset.vehicle_id
            if not vehicle or "analytic_account_id" not in vehicle._fields:
                continue
            analytic = vehicle.analytic_account_id
            if not analytic:
                continue
            distribution = {str(analytic.id): 100.0}
            if asset.analytic_distribution != distribution:
                asset.analytic_distribution = distribution

    def validate(self):
        """A fleet asset cannot start running without its vehicle."""
        self._check_fleet_asset_requirements()
        return super().validate()

    def _check_fleet_asset_requirements(self):
        """A fleet asset must name its vehicle, and carry that vehicle's analytic."""
        if "vehicle_id" not in self._fields:
            return
        for asset in self.filtered(lambda a: a.x_is_fleet and a.state != "model"):
            if not asset.vehicle_id:
                raise ValidationError(_(
                    "Asset %(asset)s uses the fleet asset model %(model)s, so a "
                    "Vehicle is required.",
                    asset=asset.display_name,
                    model=asset.model_id.display_name or _("(none)"),
                ))
            if not asset.analytic_distribution:
                raise ValidationError(_(
                    "Fleet asset %(asset)s has no analytic distribution. Set an "
                    "Analytic Account on vehicle %(vehicle)s first.",
                    asset=asset.display_name,
                    vehicle=asset.vehicle_id.display_name,
                ))

    # ------------------------------------------------------------------
    # One asset per vehicle
    # ------------------------------------------------------------------
    def _check_single_asset_per_vehicle(self):
        """A vehicle owns exactly one asset.

        Everything downstream (fleet disposal, leaseback, depreciation figures)
        resolves the asset from the vehicle, so a second asset on the same
        vehicle silently makes those flows pick one of them. Gross increases
        (``parent_id``) and asset models are not assets of their own here, and
        archived assets are ignored so a wrong record can still be parked.
        """
        if "vehicle_id" not in self._fields:
            return

        Asset = self.env["account.asset"].sudo()
        for asset in self.filtered(
            lambda a: a.vehicle_id and a.active and a.state != "model" and not a.parent_id
        ):
            other = Asset.search([
                ("vehicle_id", "=", asset.vehicle_id.id),
                ("id", "!=", asset.id),
                ("state", "!=", "model"),
                ("parent_id", "=", False),
            ], limit=1)
            if other:
                raise ValidationError(_(
                    "Vehicle %(vehicle)s is already linked to asset %(asset)s.\n"
                    "A vehicle can only own one asset. Archive or re-link the "
                    "existing asset first.",
                    vehicle=asset.vehicle_id.display_name,
                    asset=other.display_name,
                ))

    def copy_data(self, default=None):
        """A duplicate starts detached from the vehicle it was copied from."""
        vals_list = super().copy_data(default)
        for vals in vals_list:
            # ``vehicle_id`` is stored and writable, so it survives the copy even
            # though the journal items it is computed from do not. Same for the
            # analytic distribution, which points at that very vehicle.
            vals.pop("vehicle_id", None)
            vals.pop("analytic_distribution", None)
        return vals_list

    @api.model_create_multi
    def create(self, vals_list):
        assets = super().create(vals_list)
        assets._apply_vehicle_analytic_distribution()
        assets._check_single_asset_per_vehicle()
        # No fleet check here: a draft may still be incomplete, and a duplicate
        # deliberately starts without the vehicle of the asset it was copied
        # from. ``validate()`` is the gate before the asset starts running.
        return assets

    def write(self, vals):
        res = super().write(vals)
        if "vehicle_id" in vals:
            self._apply_vehicle_analytic_distribution()
        if {"vehicle_id", "active", "parent_id"} & set(vals):
            self._check_single_asset_per_vehicle()
        if {"vehicle_id", "analytic_distribution", "x_is_fleet", "model_id"} & set(vals):
            # A running asset may not lose its vehicle; a draft may still be
            # completed field by field.
            self.filtered(lambda a: a.state not in ("draft", "model"))._check_fleet_asset_requirements()
        return res

    # ------------------------------------------------------------------
    # Refinancing (leaseback / sell / dispose) tracking
    # ------------------------------------------------------------------
    @api.depends(
        "depreciation_move_ids.asset_move_type",
        "depreciation_move_ids.date",
        "depreciation_move_ids.state",
        "depreciation_move_ids.x_is_refinancing_adjustment",
        "depreciation_move_ids.x_refinancing_type",
    )
    def _compute_x_refinancing_info(self):
        for asset in self:
            event = asset._get_refinancing_move()
            asset.x_refinancing_move_id = event
            asset.x_is_refinanced = bool(event)
            asset.x_refinancing_date = event.date if event else False
            if not event:
                asset.x_refinancing_type = False
            elif event.x_refinancing_type:
                asset.x_refinancing_type = event.x_refinancing_type
            else:
                # Entries booked before this module started stamping the type.
                asset.x_refinancing_type = "sell" if event.asset_move_type == "sale" else "dispose"
            asset.x_pre_refinancing_move_id = asset._get_pre_refinancing_depreciation_move(event)

    def _get_refinancing_move(self):
        """Return the depreciation board entry closing the asset, if any.

        When several refinancing events exist (e.g. a first one was reversed and
        the asset re-opened), the latest one drives the current lifecycle of the
        asset: the earlier ones belong to a cycle that is already settled.
        """
        self.ensure_one()
        events = self.depreciation_move_ids.filtered(
            lambda m: m.asset_move_type in REFINANCING_MOVE_TYPES and m.state != "cancel"
        )
        if not events:
            return self.env["account.move"]
        return events.sorted(key=lambda m: (m.date, m._origin.id or 0))[-1]

    def _get_pre_refinancing_depreciation_move(self, event=None):
        """Last *normal* depreciation entry booked before the refinancing.

        The closing flow calls :meth:`_create_move_before_date`, which posts a
        prorata depreciation entry dated on the refinancing date itself. That
        entry belongs to the refinancing transaction, so it is excluded here -
        by its flag, and by its date for records created before the flag existed
        (``_create_move_before_date`` cancels every other entry from that date
        onwards, so the only depreciation left on that date is the prorata one).

        Returns an empty recordset when the asset was never refinanced, or when
        no depreciation was booked before it; callers then keep their own
        behaviour instead of falling back to an arbitrary value.
        """
        self.ensure_one()
        if event is None:
            event = self._get_refinancing_move()
        if not event:
            return self.env["account.move"]

        candidates = self.depreciation_move_ids.filtered(
            lambda m: (
                m.asset_move_type == "depreciation"
                and m.state != "cancel"
                and not m.x_is_refinancing_adjustment
                and m.date < event.date
            )
        )
        if not candidates:
            return self.env["account.move"]
        return candidates.sorted(key=lambda m: (m.date, m._origin.id or 0))[-1]

    def _get_refinancing_reference_values(self):
        """Depreciation snapshot downstream flows must use after a refinancing.

        Disposal calculations may not read the latest depreciation board entry
        of a refinanced asset, since that one is the refinancing itself. They
        read this snapshot instead, taken on the last normal depreciation before
        the refinancing.

        :return: ``{}`` when the asset is not refinanced (or has no depreciation
            before the refinancing), so the caller keeps its regular behaviour.
        """
        self.ensure_one()
        move = self.x_pre_refinancing_move_id
        if not move:
            return {}
        return {
            "reference_move_id": move.id,
            "reference_date": move.date,
            "monthly_depreciation": abs(move.depreciation_value),
            "accumulated_depreciation": abs(move.asset_depreciated_value),
            "book_value": move.asset_remaining_value + self.salvage_value,
        }

    def _create_move_before_date(self, date):
        """Flag the prorata depreciation created as part of a refinancing."""
        known_move_ids = set(self.depreciation_move_ids.ids)
        res = super()._create_move_before_date(date)
        if self.env.context.get("x_asset_refinancing_close"):
            new_moves = self.depreciation_move_ids.filtered(lambda m: m.id not in known_move_ids)
            if new_moves:
                new_moves.write({"x_is_refinancing_adjustment": True})
        return res

    def set_to_close(self, invoice_line_ids, date=None, message=None):
        """Stamp the refinancing type on the native Sell / Dispose closing."""
        assets = self + self.children_ids
        known_move_ids = {asset.id: set(asset.depreciation_move_ids.ids) for asset in assets}
        res = super(
            AccountAsset, self.with_context(x_asset_refinancing_close=True)
        ).set_to_close(invoice_line_ids, date=date, message=message)

        refinancing_type = "sell" if invoice_line_ids else "dispose"
        for asset in assets:
            new_moves = asset.depreciation_move_ids.filtered(
                lambda m: m.id not in known_move_ids[asset.id]
                and m.asset_move_type in REFINANCING_MOVE_TYPES
            )
            if new_moves:
                new_moves.write({"x_refinancing_type": refinancing_type})
        return res

    def set_to_close_leaseback(self, ar_account, ar_amount, deferred_account, date=None, message=None):
        """Close an asset through a leaseback (a Sell without an invoice).

        Mirrors the native ``set_to_close`` flow used by Sell/Dispose but the
        proceeds come from a manual A/R amount instead of a customer invoice,
        and the gain/loss versus the book value is booked to a single deferred
        profit/loss account.
        """
        self.ensure_one()
        disposal_date = date or fields.Date.today()
        if disposal_date <= self.company_id._get_user_fiscal_lock_date(self.journal_id):
            raise UserError(_("You cannot process a leaseback before the lock date."))
        if self.children_ids.filtered(lambda a: a.state in ("draft", "open") or a.value_residual > 0):
            raise UserError(_(
                "You cannot automate the journal entry for an asset that has a "
                "running gross increase. Please 'Dispose' the increase(s) first."
            ))

        self.state = "close"
        move_ids = self._get_leaseback_moves(ar_account, ar_amount, deferred_account, disposal_date)
        self.message_post(body=_("Asset leased back. %s", message if message else ""))

        if move_ids:
            return {
                "name": _("Leaseback Move"),
                "view_mode": "form",
                "res_model": "account.move",
                "type": "ir.actions.act_window",
                "target": "current",
                "res_id": move_ids[0],
                "domain": [("id", "in", move_ids)],
            }

    def _get_leaseback_moves(self, ar_account, ar_amount, deferred_account, disposal_date):
        """Create the leaseback disposal move for every asset in ``self``.

        Journal (positive asset, following the Leaseback specification):

            Cr  Asset account            original value
            Dr  Accumulated Depreciation depreciated to date
            Dr  A/R Account              A/R Amount
            Cr/Dr Deferred Profit/Loss   gain -> credit, loss -> debit
        """
        move_ids = []
        for asset in self:
            asset.with_context(x_asset_refinancing_close=True)._create_move_before_date(disposal_date)

            currency = asset.currency_id
            analytic_distribution = asset.analytic_distribution
            name = _("%(asset)s: Leaseback", asset=asset.name)

            original_value = asset.original_value
            initial_account = (
                asset.original_move_line_ids.account_id
                if len(asset.original_move_line_ids.account_id) == 1
                else asset.account_asset_id
            )
            lines_before = asset.depreciation_move_ids.filtered(
                lambda m: m.date <= disposal_date and m.asset_move_type != "sale"
            )
            depreciated_amount = currency.round(
                sum(lines_before.mapped("depreciation_value")) + asset.already_depreciated_amount_import
            )
            book_value = currency.round(original_value - depreciated_amount)
            gain_loss = currency.round(ar_amount - book_value)

            line_ids = [
                Command.create({
                    "name": name,
                    "account_id": initial_account.id,
                    "debit": 0.0,
                    "credit": original_value,
                    "analytic_distribution": analytic_distribution,
                }),
                Command.create({
                    "name": name,
                    "account_id": asset.account_depreciation_id.id,
                    "debit": depreciated_amount,
                    "credit": 0.0,
                    "analytic_distribution": analytic_distribution,
                }),
                Command.create({
                    "name": name,
                    "account_id": ar_account.id,
                    "debit": ar_amount,
                    "credit": 0.0,
                }),
            ]
            if currency.compare_amounts(gain_loss, 0) < 0:
                line_ids.append(Command.create({
                    "name": name,
                    "account_id": deferred_account.id,
                    "debit": -gain_loss,
                    "credit": 0.0,
                    "analytic_distribution": analytic_distribution,
                }))
            else:
                line_ids.append(Command.create({
                    "name": name,
                    "account_id": deferred_account.id,
                    "debit": 0.0,
                    "credit": gain_loss,
                    "analytic_distribution": analytic_distribution,
                }))

            vals = {
                "asset_id": asset.id,
                "ref": name,
                "asset_depreciation_beginning_date": disposal_date,
                "date": disposal_date,
                "journal_id": asset.journal_id.id,
                "move_type": "entry",
                "asset_move_type": "sale",
                "x_refinancing_type": "leaseback",
                "line_ids": line_ids,
            }
            asset.write({
                "depreciation_move_ids": [Command.create(vals)],
                "leaseback_deferred_pl_amount": gain_loss,
            })
            asset.net_gain_on_sale = gain_loss
            move_ids += self.env["account.move"].search(
                [("asset_id", "=", asset.id), ("state", "=", "draft"), ("asset_move_type", "=", "sale")]
            ).ids

        return move_ids
