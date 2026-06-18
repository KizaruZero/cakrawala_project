from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class DisposalBidding(models.Model):
    _name = "disposal.bidding"
    _description = "Disposal Bidding"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "id desc"

    _PPN_RATE = 0.11

    name = fields.Char(string="BID Number", required=True, copy=False, readonly=True, default="/")
    vehicle_id = fields.Many2one(
        "fleet.vehicle",
        string="Vehicle",
        required=True,
        ondelete="restrict",
        domain=[("fleet_sub_status_id.is_disposal", "=", True)],
    )
    asset_number = fields.Char(
        string="Asset Number",
        related="vehicle_id.fleet_document_asset_number",
        store=True,
        readonly=True,
    )
    license_plate = fields.Char(
        string="License Plate",
        related="vehicle_id.fleet_document_license_plate",
        store=True,
        readonly=True,
    )
    currency_id = fields.Many2one("res.currency", string="Currency", default=lambda self: self.env.company.currency_id)
    start_date = fields.Date(string="Start Date")
    end_date = fields.Date(string="End Date")
    open_price = fields.Monetary(string="Open Price", currency_field="currency_id")
    sales_price = fields.Monetary(string="Sales Price", currency_field="currency_id", compute="_compute_sales_price", store=True)
    potential_winner = fields.Char(string="Potential Winner", compute="_compute_potential_winner", store=True)
    sale_order_id = fields.Many2one(
        "sale.order",
        string="Sales Order",
        readonly=True,
        copy=False,
    )
    sale_order_count = fields.Integer(string="Sales Order Count", compute="_compute_sale_order_count")
    state = fields.Selection([
        ("draft", "Draft"),
        ("waiting_approval", "Waiting Approval"),
        ("approved", "Approved"),
        ("rejected", "Rejected"),
    ], string="State", default="draft", tracking=True)
    is_editable = fields.Boolean(string='Is Editable', compute='_compute_is_editable')

    disposal_aging = fields.Char(string="Aging", readonly=True)
    disposal_monthly_depreciation = fields.Monetary(string="Monthly Depreciation", currency_field="currency_id", readonly=True)
    disposal_accum_depreciation = fields.Monetary(string="Accum Depreciation", currency_field="currency_id", readonly=True)
    disposal_book_value = fields.Monetary(string="Book Value", currency_field="currency_id", readonly=True)
    disposal_total_service = fields.Monetary(string="Total Service", currency_field="currency_id", readonly=True)
    disposal_rbs_percentage = fields.Float(string="%RBS", readonly=True)
    disposal_bpkb_location = fields.Char(string="BPKB Location", readonly=True)
    disposal_phd = fields.Monetary(string="PHD", currency_field="currency_id", readonly=True)
    disposal_penalti_pelunasan = fields.Monetary(string="Penalti Pelunasan", currency_field="currency_id", default=0.0)
    disposal_sisa_laba_rugi_ditangguhkan = fields.Monetary(string="Sisa Laba Rugi Ditangguhkan", currency_field="currency_id", default=0.0)
    selling_target_tax_id = fields.Many2one(
        "account.tax",
        string="Taxes",
        domain=[("type_tax_use", "=", "sale")],
        ondelete="restrict",
    )
    selling_target_include_ppn = fields.Monetary(string="Include PPN", currency_field="currency_id", readonly=True)
    selling_target_exclude_ppn = fields.Monetary(string="Exclude PPN", currency_field="currency_id", readonly=True)
    selling_target_profit_loss_amount = fields.Monetary(string="Profit/Loss", currency_field="currency_id", readonly=True)
    selling_target_profit_loss_percentage = fields.Float(string="%Profit/Loss", readonly=True)

    bidding_line_ids = fields.One2many("disposal.bidding.line", "bidding_id", string="Bidding Lines")

    approval_tracking_ids = fields.One2many('disposal.approval.tracking', 'bidding_id', string='Approval Tracking')
    next_approver_id = fields.Many2one('res.users', string='Current Approver', compute='_compute_next_approver', store=True)
    can_current_user_approve = fields.Boolean(string='Can Current User Approve', compute='_compute_current_user_approval')
    can_current_user_delegate = fields.Boolean(string='Can Current User Delegate', compute='_compute_current_user_approval')
    current_user_approval_id = fields.Many2one('disposal.approval.tracking', string='Current User Approval', compute='_compute_current_user_approval')
    current_pending_approval_id = fields.Many2one('disposal.approval.tracking', string='Current Pending Approval', compute='_compute_current_user_approval')

    @api.depends("sale_order_id")
    def _compute_sale_order_count(self):
        for rec in self:
            rec.sale_order_count = 1 if rec.sale_order_id else 0

    @api.depends('bidding_line_ids.bidding_price')
    def _compute_sales_price(self):
        for rec in self:
            if rec.bidding_line_ids:
                rec.sales_price = max(rec.bidding_line_ids.mapped('bidding_price') or [0])
            else:
                rec.sales_price = 0

    @api.depends('bidding_line_ids.bidding_price', 'bidding_line_ids.partner_id')
    def _compute_potential_winner(self):
        for rec in self:
            if rec.bidding_line_ids:
                highest_bid_line = max(rec.bidding_line_ids, key=lambda l: l.bidding_price or 0, default=None)
                rec.potential_winner = highest_bid_line.partner_id.display_name if highest_bid_line else ""
            else:
                rec.potential_winner = ""

    @api.depends('approval_tracking_ids.state')
    def _compute_next_approver(self):
        for rec in self:
            pending = rec.approval_tracking_ids.filtered(lambda t: t.state == 'pending').sorted(key=lambda r: (r.sequence, r.id))
            rec.next_approver_id = pending[:1].approver_id if pending else False

    @api.depends('approval_tracking_ids.state', 'approval_tracking_ids.approver_id', 'approval_tracking_ids.delegate_id', 'state')
    def _compute_current_user_approval(self):
        current_user = self.env.user
        is_admin = current_user.has_group('base.group_system')
        today = fields.Date.context_today(self)

        for request in self:
            next_pending = request.approval_tracking_ids.filtered(lambda t: t.state == 'pending').sorted(key=lambda t: (t.sequence, t.id))[:1]

            request.current_pending_approval_id = next_pending or False

            is_approver = next_pending and next_pending.approver_id == current_user
            is_valid_delegate = (next_pending and next_pending.delegate_id == current_user and next_pending._is_delegate_valid(today))

            if request.state == 'waiting_approval' and (is_approver or is_valid_delegate):
                request.can_current_user_approve = True
                request.current_user_approval_id = next_pending
            else:
                request.can_current_user_approve = False
                request.current_user_approval_id = False

            request.can_current_user_delegate = bool(
                request.state == 'waiting_approval' and next_pending and (next_pending.approver_id == current_user or is_admin)
            )

    # def _get_sale_order_from_vehicle(self):
    #     self.ensure_one()
    #     vehicle = self.vehicle_id
    #     if not vehicle:
    #         return self.env["sale.order"]

    #     SaleOrder = self.env["sale.order"].sudo()
    #     if "disposal_vehicle_id" in SaleOrder._fields:
    #         order = SaleOrder.search([("disposal_vehicle_id", "=", vehicle.id)], order="date_order desc, id desc", limit=1)
    #         if order:
    #             return order

    #     for field_name in ("vehicle_id", "fleet_vehicle_id", "x_vehicle_id"):
    #         if field_name in SaleOrder._fields:
    #             order = SaleOrder.search([(field_name, "=", vehicle.id)], order="date_order desc, id desc", limit=1)
    #             if order:
    #                 return order

    #     SaleOrderLine = self.env["sale.order.line"].sudo()
    #     for field_name in ("vehicle_id", "fleet_vehicle_id", "x_vehicle_id"):
    #         if field_name in SaleOrderLine._fields:
    #             line = SaleOrderLine.search([(field_name, "=", vehicle.id)], order="id desc", limit=1)
    #             if line.order_id:
    #                 return line.order_id

    #     lot = self._get_vehicle_stock_lot()
    #     if lot:
    #         line = SaleOrderLine.search([("product_id", "=", lot.product_id.id)], order="id desc", limit=1)
    #         if line.order_id:
    #             return line.order_id

    #     return self.env["sale.order"]

    # @api.onchange("vehicle_id")
    # def _onchange_vehicle_id_set_sale_order(self):
    #     for rec in self:
    #         rec.sale_order_id = rec._get_sale_order_from_vehicle() if rec.vehicle_id else False

    @api.model_create_multi
    def create(self, vals_list):
        today = fields.Date.context_today(self)
        Seq = self.env['ir.sequence'].with_company(self.env.company)
        for vals in vals_list:
            if not vals.get('name') or vals.get('name') == '/':
                vals['name'] = Seq.next_by_code('disposal.bidding', sequence_date=today)
                if not vals['name']:
                    raise ValidationError(
                        'Sequence dengan kode "disposal.bidding" tidak ditemukan untuk perusahaan ini. '
                        'Buat atau perbaiki di Pengaturan → Teknis → Sequences.'
                    )
            # if vals.get("vehicle_id") and not vals.get("sale_order_id"):
            #     rec = self.new(vals)
            #     sale_order = rec._get_sale_order_from_vehicle()
            #     if sale_order:
            #         vals["sale_order_id"] = sale_order.id
        return super().create(vals_list)

    def _post_approval_actions(self):
        for rec in self:
            sale_order = rec._create_sale_order()
            rec.message_post(body=_('Bidding approved. Sales Order created: %s') % sale_order.display_name)

    def _get_winner_line(self):
        self.ensure_one()
        winner = self.bidding_line_ids.sorted(key=lambda line: (line.bidding_price or 0, line.id), reverse=True)[:1]
        if not winner:
            raise ValidationError(_('Add at least one bidding line before final approval.'))
        if not winner.partner_id:
            raise ValidationError(_('The winning bidding line must have a Showroom / Vendor.'))
        if not winner.bidding_price:
            raise ValidationError(_('The winning bidding line must have a bidding price.'))
        return winner

    def _get_vehicle_sale_product(self):
        self.ensure_one()
        vehicle = self.vehicle_id
        lot = self._get_vehicle_stock_lot()
        if lot:
            return lot.product_id

        if "product_id" in vehicle._fields and vehicle.product_id:
            return vehicle.product_id

        product = self.env["product.product"].search([
            ("is_vehicle", "=", True),
            ("name", "=", vehicle.model_id.name),
        ], limit=1)
        if product:
            return product

        raise ValidationError(
            _("No sale product found for vehicle %s. Set the vehicle product or make sure its asset serial/lot has a product.")
            % vehicle.display_name
        )

    def _get_vehicle_stock_lot(self):
        self.ensure_one()
        vehicle = self.vehicle_id
        asset_names = [
            vehicle.fleet_document_asset_number,
            vehicle.asset_number,
        ]
        names = [name for name in asset_names if name]
        if not names:
            return self.env["stock.lot"]
        return self.env["stock.lot"].search([
            ("name", "in", names),
            ("product_id", "!=", False),
        ], limit=1)

    def _get_vehicle_analytic_distribution(self):
        self.ensure_one()
        analytic = self.vehicle_id.analytic_account_id
        return {str(analytic.id): 100.0} if analytic else False

    def _prepare_sale_order_vals(self):
        self.ensure_one()
        winner = self._get_winner_line()
        product = self._get_vehicle_sale_product()
        analytic_distribution = self._get_vehicle_analytic_distribution()
        line_vals = {
            "product_id": product.id,
            "product_uom_qty": 1.0,
            "price_unit": winner.bidding_price,
            "name": "%s - %s" % (self.name, self.vehicle_id.display_name),
        }
        if analytic_distribution and "analytic_distribution" in self.env["sale.order.line"]._fields:
            line_vals["analytic_distribution"] = analytic_distribution

        return {
            "partner_id": winner.partner_id.id,
            "origin": self.name,
            "disposal_bidding_id": self.id,
            "disposal_vehicle_id": self.vehicle_id.id,
            "order_line": [(0, 0, line_vals)],
        }

    def _create_sale_order(self):
        self.ensure_one()
        if self.sale_order_id:
            return self.sale_order_id

        sale_order = self.env["sale.order"].create(self._prepare_sale_order_vals())
        self.with_context(x_disposal_post_approval=True).sale_order_id = sale_order.id
        return sale_order

    def action_view_sale_order(self):
        self.ensure_one()
        if not self.sale_order_id:
            raise ValidationError(_('No Sales Order has been created for this Bidding.'))
        return {
            "type": "ir.actions.act_window",
            "name": _("Sales Order"),
            "res_model": "sale.order",
            "res_id": self.sale_order_id.id,
            "view_mode": "form",
            "target": "current",
        }

    def action_print_out(self):
        self.ensure_one()
        return self.env.ref("x_disposal.action_report_disposal_bidding").report_action(self)

    def action_submit_for_approval(self):
        self._check_submission_requirements()
        for rec in self:
            rec._generate_approval_lines()
            rec.state = 'waiting_approval'
            rec._send_next_approver_notification(is_reminder=False)

    def _check_submission_requirements(self):
        for rec in self:
            if not rec.open_price:
                raise ValidationError('Open Price must be set before submit for approval.')
            if not rec.bidding_line_ids:
                raise ValidationError('Add at least one bidding line before submit for approval.')

    def _generate_approval_lines(self):
        self.ensure_one()
        old_pending = self.approval_tracking_ids.filtered(lambda x: x.state == 'pending')
        if old_pending:
            old_pending.write({'state': 'cancelled', 'date': fields.Datetime.now()})

        # Use the generic disposal approval matrix.
        matrix = self.env['disposal.approval.matrix'].search([
            ('active', '=', True),
            ('is_default', '=', False),
        ], limit=1)

        if not matrix:
            matrix = self.env['disposal.approval.matrix'].search([
                ('active', '=', True), ('is_default', '=', True)
            ], limit=1)

        if not matrix:
            raise ValidationError('No approval matrix found. Please configure an approval matrix.')

        applicable = matrix.approval_line_ids.filtered(lambda l: l.active and l.starting_amount <= (self.open_price or 0)).sorted(key=lambda l: l.sequence)
        if not applicable:
            raise ValidationError('No approval line matched for this Bidding amount. Please review the approval matrix.')

        for line in applicable:
            approver = line.approver_id
            if not approver or not approver.active or approver.share:
                approver = self._get_default_approver_user()
            if not approver:
                raise ValidationError('No valid approver found. Please configure a valid approver.')

            self.env['disposal.approval.tracking'].create({
                'bidding_id': self.id,
                'sequence': line.sequence,
                'approver_id': approver.id,
                'delegate_id': line.delegate_id.id if line.delegate_id else False,
                'delegate_valid_from': line.delegate_valid_from or False,
                'delegate_valid_to': line.delegate_valid_to or False,
                'state': 'pending',
            })

    def _get_default_approver_user(self):
        current_user = self.env.user
        if current_user.active and not current_user.share and current_user.login != 'admin':
            return current_user
        return self.env['res.users'].search([('active', '=', True), ('share', '=', False), ('login', '!=', 'admin')], order='id asc', limit=1)

    def _send_next_approver_notification(self, is_reminder=False):
        for rec in self:
            if rec.state != 'waiting_approval' or not rec.next_approver_id:
                continue
            message = ('Reminder: %s is waiting your approval.' if is_reminder else '%s is waiting for your approval.') % rec.name
            rec.activity_schedule('mail.mail_activity_data_todo', user_id=rec.next_approver_id.id, summary='Bidding Approval', note=message)
            rec.message_post(body=message)

    def _open_approval_action_wizard(self, action_type):
        self.ensure_one()
        if not self.can_current_user_approve or not self.current_user_approval_id:
            raise ValidationError('You are not allowed to process this Bidding at the current approval stage.')
        return {
            'type': 'ir.actions.act_window',
            'name': 'Bidding Approval Action',
            'res_model': 'disposal.approval.action.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_bidding_id': self.id,
                'default_approval_tracking_id': self.current_user_approval_id.id,
                'default_action_type': action_type,
            }
        }

    def action_open_accept_wizard(self):
        self.ensure_one()
        return self._open_approval_action_wizard('approve')

    def action_open_reject_wizard(self):
        self.ensure_one()
        return self._open_approval_action_wizard('reject')

    def action_approve(self):
        for rec in self:
            if not rec.current_pending_approval_id:
                raise ValidationError('No pending approval stage found for this Bidding.')
            rec.current_pending_approval_id.action_approve()

    def action_reject(self):
        for rec in self:
            if not rec.current_pending_approval_id:
                raise ValidationError('No pending approval stage found for this Bidding.')
            rec.current_pending_approval_id.action_reject()
            
    def action_reset_to_draft(self):
        for rec in self:
            rec.state = 'draft'
            rec.message_post(body='Bidding reset to draft.')
            rec.bidding_line_ids.unlink()

    @api.depends('state')
    def _compute_is_editable(self):
        for rec in self:
            rec.is_editable = False if rec.state == 'approved' else True

    def _first_existing_field_value(self, record, field_names, default=False):
        for field_name in field_names:
            if field_name in record._fields:
                value = record[field_name]
                if value not in (False, None):
                    return value
        return default

    def _get_vehicle_asset(self):
        self.ensure_one()
        if "account.asset" not in self.env.registry:
            return False

        Asset = self.env["account.asset"].sudo()
        vehicle = self.vehicle_id
        relational_fields = ("vehicle_id", "fleet_vehicle_id", "x_vehicle_id")
        for field_name in relational_fields:
            if field_name in Asset._fields:
                asset = Asset.search([(field_name, "=", vehicle.id)], limit=1)
                if asset:
                    return asset

        candidates = [
            vehicle.fleet_document_asset_number,
            vehicle.asset_number if "asset_number" in vehicle._fields else False,
            vehicle.license_plate,
            vehicle.fleet_document_license_plate,
        ]
        values = [value for value in candidates if value]
        if not values:
            return Asset

        domain = []
        for field_name in ("asset_number", "code", "name"):
            if field_name not in Asset._fields:
                continue
            part = [(field_name, "in", values)]
            domain = part if not domain else ["|"] + domain + part
        return Asset.search(domain, limit=1) if domain else Asset

    def _asset_is_running(self, asset):
        state = self._first_existing_field_value(asset, ("state", "asset_state"))
        return state in ("open", "running", "posted")

    def _get_depreciation_board_line(self, asset, posted=False):
        line_models = ("account.asset.depreciation.line", "account.asset.line")
        for model_name in line_models:
            if model_name not in self.env.registry:
                continue
            Line = self.env[model_name].sudo()
            if "asset_id" not in Line._fields:
                continue
            domain = [("asset_id", "=", asset.id)]
            if "move_id" in Line._fields:
                domain.append(("move_id", "!=" if posted else "=", False))
            if "move_check" in Line._fields:
                domain.append(("move_check", "=", posted))
            if "parent_state" in Line._fields and posted:
                domain.append(("parent_state", "=", "posted"))
            order = "depreciation_date desc, id desc" if "depreciation_date" in Line._fields else "id desc"
            return Line.search(domain, order=order, limit=1)
        return self.env["account.move"]

    def _get_posted_depreciation_moves(self, asset):
        if "account.move" not in self.env.registry:
            return False

        Move = self.env["account.move"].sudo()
        domain = [("state", "=", "posted")]
        if "asset_id" in Move._fields:
            domain.append(("asset_id", "=", asset.id))
        elif "account.move.line" in self.env.registry and "asset_id" in self.env["account.move.line"]._fields:
            moves = self.env["account.move.line"].sudo().search([("asset_id", "=", asset.id), ("move_id.state", "=", "posted")]).mapped("move_id")
            return moves.sorted(key=lambda move: (move.date or fields.Date.from_string("1900-01-01"), move.id), reverse=True)
        else:
            return Move
        return Move.search(domain, order="date desc, id desc")

    def _format_depreciation_aging(self, line):
        if not line:
            return False
        value = self._first_existing_field_value(
            line,
            ("sequence", "depreciation_sequence", "depreciation_number", "name"),
        )
        if value:
            return str(value)
        depreciation_date = self._first_existing_field_value(line, ("depreciation_date", "date"))
        return str(depreciation_date) if depreciation_date else False

    def _get_unit_information_values(self):
        self.ensure_one()
        asset = self._get_vehicle_asset()
        if not asset or not self._asset_is_running(asset):
            return {
                "disposal_aging": False,
                "disposal_monthly_depreciation": 0.0,
                "disposal_accum_depreciation": 0.0,
                "disposal_book_value": 0.0,
                "disposal_total_service": 0.0,
                "disposal_rbs_percentage": 0.0,
                "disposal_bpkb_location": False,
                "disposal_phd": 0.0,
            }

        original_value = self._first_existing_field_value(asset, ("original_value", "value", "gross_value"), 0.0) or 0.0
        method_number = self._first_existing_field_value(asset, ("method_number", "method_period_number"), 0.0) or 0.0
        monthly_depreciation = original_value / method_number if method_number else 0.0

        accum_depreciation = self._first_existing_field_value(
            asset,
            ("asset_depreciated_value", "value_depreciated", "depreciated_value"),
            0.0,
        ) or 0.0
        posted_moves = self._get_posted_depreciation_moves(asset)
        if posted_moves:
            latest_move = posted_moves[:1]
            accum_depreciation = self._first_existing_field_value(
                latest_move,
                ("asset_depreciated_value", "value_depreciated", "depreciated_value"),
                accum_depreciation,
            ) or accum_depreciation

        book_value = self._first_existing_field_value(asset, ("book_value", "value_residual"), 0.0) or 0.0
        service_domain = [("vehicle_id", "=", self.vehicle_id.id), ("state", "=", "approved")]
        total_service = sum(self.env["fleet.spk"].sudo().search(service_domain).mapped("total_service_amount"))
        rbs_base = accum_depreciation + book_value
        rbs = (total_service / rbs_base * 100) if rbs_base else 0.0

        Contract = self.env["fleet.vehicle.log.contract"].sudo()
        bpkb_location = False
        if "cost_subtype_id" in Contract._fields and "bpkb_location" in Contract._fields:
            contract = Contract.search([
                ("vehicle_id", "=", self.vehicle_id.id),
                ("cost_subtype_id.name", "=", "STNK"),
                ("state", "=", "open"),
            ], order="start_date desc, id desc", limit=1)
            bpkb_location = contract.bpkb_location if contract else False

        penalty = self.disposal_penalti_pelunasan or 0.0
        deferred = self.disposal_sisa_laba_rugi_ditangguhkan or 0.0
        phd = book_value + (book_value * self._PPN_RATE) + penalty - deferred
        aging = self._format_depreciation_aging(self._get_depreciation_board_line(asset, posted=False))

        return {
            "disposal_aging": aging,
            "disposal_monthly_depreciation": monthly_depreciation,
            "disposal_accum_depreciation": accum_depreciation,
            "disposal_book_value": book_value,
            "disposal_total_service": total_service,
            "disposal_rbs_percentage": rbs,
            "disposal_bpkb_location": bpkb_location,
            "disposal_phd": phd,
        }

    def _apply_unit_information_values(self):
        for rec in self:
            values = rec._get_unit_information_values()
            values["open_price"] = values.get("disposal_phd") or 0.0
            rec.write(values)

    def _get_selling_target_values(self):
        self.ensure_one()

        if not self.selling_target_tax_id:
            raise ValidationError(_("Please select Taxes before computing Selling Target."))

        sales_price = self.sales_price or 0
        tax_values = self.selling_target_tax_id.compute_all(
            sales_price,
            currency=self.currency_id,
            quantity=1.0,
        )
        include_ppn = tax_values["total_included"]
        exclude_ppn = include_ppn - sales_price
        book_value = self.disposal_book_value or 0
        penalty = self.disposal_penalti_pelunasan or 0
        deferred = self.disposal_sisa_laba_rugi_ditangguhkan or 0

        profit_loss_amount = exclude_ppn - book_value - penalty + deferred
        profit_loss_percentage = (profit_loss_amount / book_value * 100) if book_value else 0

        return {
            'selling_target_include_ppn': include_ppn,
            'selling_target_exclude_ppn': exclude_ppn,
            'selling_target_profit_loss_amount': profit_loss_amount,
            'selling_target_profit_loss_percentage': profit_loss_percentage,
        }

    def _apply_selling_target_values(self):
        for rec in self:
            values = rec._get_selling_target_values()
            for field_name, value in values.items():
                setattr(rec, field_name, value)

    def action_compute_unit_information(self):
        self.ensure_one()
        self._apply_unit_information_values()
        return True

    def action_generate_phd(self):
        self.ensure_one()
        values = self._get_unit_information_values()
        self.write({
            "disposal_phd": values["disposal_phd"],
            "open_price": values["disposal_phd"] or 0.0,
        })
        self.message_post(body=_("PHD generated: %s") % self.disposal_phd)
        return True

    def action_compute_profit_loss(self):
        self.ensure_one()
        self._apply_selling_target_values()

    def write(self, vals):
        if not self.env.context.get("x_disposal_post_approval"):
            for rec in self:
                if rec.state == 'approved':
                    raise ValidationError('Cannot modify a Bidding after it has been approved.')
        return super(DisposalBidding, self).write(vals)

    def unlink(self):
        for rec in self:
            if rec.state == 'approved':
                raise ValidationError('Cannot delete a Bidding after it has been approved.')
        return super(DisposalBidding, self).unlink()


class DisposalBiddingLine(models.Model):
    _name = "disposal.bidding.line"
    _description = "Disposal Bidding Line"

    bidding_id = fields.Many2one('disposal.bidding', string='Bidding', required=True, ondelete='cascade')
    sequence = fields.Integer(string='Sequence', default=10)
    partner_id = fields.Many2one(
        'res.partner',
        string='Showroom / Vendor',
        required=True,
        ondelete='restrict',
    )
    pic_name = fields.Char(string='PIC Name')
    bidding_price = fields.Float(string='Bidding Price', required=True)
    notes = fields.Text(string='Notes')
    attachment = fields.Binary(string='Attachment', attachment=True, required=True)
    attachment_filename = fields.Char(string='Attachment Filename')

    def write(self, vals):
        for rec in self:
            if rec.bidding_id and rec.bidding_id.state == 'approved':
                raise ValidationError('Cannot modify bidding lines after Bidding is approved.')
        return super(DisposalBiddingLine, self).write(vals)

    def unlink(self):
        for rec in self:
            if rec.bidding_id and rec.bidding_id.state == 'approved':
                raise ValidationError('Cannot delete bidding lines after Bidding is approved.')
        return super(DisposalBiddingLine, self).unlink()

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            bidding_id = vals.get('bidding_id')
            if bidding_id:
                bidding = self.env['disposal.bidding'].browse(bidding_id)
                if bidding and bidding.state == 'approved':
                    raise ValidationError('Cannot add bidding lines after Bidding is approved.')
        return super(DisposalBiddingLine, self).create(vals_list)

