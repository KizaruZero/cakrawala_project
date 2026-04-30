from odoo import models, fields, api
from odoo.exceptions import ValidationError


class FleetSPK(models.Model):
    _name = "fleet.spk"
    _description = "Surat Perintah Kerja (SPK)"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "id desc"

    # === Basic Fields ===
    name = fields.Char(
        string="SPK Number",
        required=True,
        copy=False,
        readonly=True,
        default="/"
    )
    state = fields.Selection(
        [
            ("new", "New"),
            ("waiting_approval", "Waiting Approval"),
            ("approved", "Approved"),
            ("done", "Done"),
            ("rejected", "Rejected"),
            ("received", "Invoice Received"),
        ],
        string="State",
        default="new",
        tracking=True,
    )
    execution_type_id = fields.Many2one(
        "spk.execution.type",
        string="Execution Type",
        required=True,
        ondelete="restrict",
        default=lambda self: self.env["spk.execution.type"].search(
            [("code", "=", "scheduled")], limit=1
        ),
    )
    execution_type = fields.Char(
        string="Execution Type Code",
        related="execution_type_id.code",
        store=True,
        readonly=True,
    )
    category = fields.Selection(
        [
            ("internal", "Internal"),
            ("external", "External"),
        ],
        string="Category",
        required=True,
    )
    maintenance_type_id = fields.Many2one(
        "spk.maintenance.type",
        string="Maintenance Type",
        required=True,
        ondelete="restrict",
        default=lambda self: self.env["spk.maintenance.type"].search(
            [("code", "=", "schedule")], limit=1
        ),
    )
    maintenance_type = fields.Char(
        string="Maintenance Type Code",
        related="maintenance_type_id.code",
        store=True,
        readonly=True,
    )

    # === Related Entities ===
    vehicle_id = fields.Many2one(
        "fleet.vehicle",
        string="Vehicle",
        required=True,
        ondelete="restrict",
    )
    vendor_id = fields.Many2one(
        "res.partner",
        string="Vendor (Bengkel)",
        domain="[('is_company', '=', True)]",
        required=False,
    )
    vendor_name = fields.Char(
        string="Vendor (Bengkel)",
    )
    customer_name = fields.Char(
        string="Customer",
    )
    pic_client_name = fields.Char(
        string="PIC Client",
    )
    bak_id = fields.Char(
        string="BAK Form Number",
        help="BAK (Berita Acara Kendaraan) form reference number.",
    )
    bak_reference = fields.Char(
        string="BAK Reference",
    )

    goods_issue_source_id = fields.Many2one(
        "stock.picking.type",
        string="Goods Issue Source",
        domain="[('code', '=', 'outgoing')]",
    )
    description = fields.Text(
        string="Description",
        required=True,
    )
    currency = fields.Char(
        string="Currency",
        default="IDR",
    )

    customer_id = fields.Many2one('res.partner', string='Customer')
    pic_client = fields.Char(string='PIC Client', help='Free text field for PIC (Person In Charge) Client name')
    currency_id = fields.Many2one('res.currency', string='Currency', default=lambda self: self.env.company.currency_id)

    # === Vehicle Details (from vehicle_id) ===
    spk_date = fields.Date(
        string="SPK Date",
        default=fields.Date.today,
        required=True,
    )
    planning_date = fields.Date(string="Planning Date")
    license_plate = fields.Char(
        string="License Plate",
        related="vehicle_id.license_plate",
        store=True,
        readonly=True,
    )
    color = fields.Char(
        string="Color",
        related="vehicle_id.color",
        store=True,
        readonly=True,
    )
    year = fields.Char(
        string="Year",
        compute="_compute_vehicle_snapshot",
        store=True,
        readonly=True,
    )
    vin_sn = fields.Char(
        string="VIN/SN",
        related="vehicle_id.vin_sn",
        store=True,
        readonly=True,
    )
    engine_number = fields.Char(
        string="Engine Number",
        related="vehicle_id.engine_number",
        store=True,
        readonly=True,
    )
    odometer = fields.Float(
        string="Odometer (km)",
        required=False,
    )
    last_service = fields.Date(
        string="Last Service Date",
        readonly=True,
    )

    # === One2many Relations ===
    sparepart_line_ids = fields.One2many(
        "spk.sparepart.line",
        "spk_id",
        string="Spare Parts",
    )
    service_line_ids = fields.One2many(
        "spk.service.line",
        "spk_id",
        string="Services",
    )
    tyre_detail_ids = fields.One2many(
        "spk.tyre.line",
        "spk_id",
        string="Tyre Details",
    )
    aki_detail_ids = fields.One2many(
        "spk.aki.line",
        "spk_id",
        string="AKI Details",
    )
    on_risk_product_ids = fields.One2many(
        "spk.on.risk.product.line",
        "spk_id",
        string="Products On Risk",
    )

    approval_tracking_ids = fields.One2many(
        'spk.approval.tracking', 'spk_id',
        string="Approval Tracking",
    )
    next_approver_id = fields.Many2one(
        "res.users",
        string="Current Approver",
        compute="_compute_next_approver",
        store=True,
        tracking=True,
    )
    can_current_user_approve = fields.Boolean(
        string="Can Current User Approve",
        compute="_compute_current_user_approval",
    )
    can_current_user_delegate = fields.Boolean(
        string="Can Current User Delegate",
        compute="_compute_current_user_approval",
    )
    current_user_approval_id = fields.Many2one(
        "spk.approval.tracking",
        string="Current User Approval",
        compute="_compute_current_user_approval",
    )
    current_pending_approval_id = fields.Many2one(
        "spk.approval.tracking",
        string="Current Pending Approval",
        compute="_compute_current_user_approval",
    )

    # === Totals ===
    total_sparepart_amount = fields.Float(
        string="Total Spare Parts",
        compute="_compute_totals",
    )
    total_service_amount = fields.Float(
        string="Total Services",
        compute="_compute_totals",
    )
    total_amount = fields.Float(
        string="Total Amount",
        compute="_compute_totals",
    )

    po_id = fields.Many2one(
        "purchase.order",
        string="Generated PO",
        readonly=True,
    )

    @api.depends(
        "sparepart_line_ids.subtotal",
        "service_line_ids.subtotal",
        "on_risk_product_ids.subtotal",
    )
    def _compute_totals(self):
        for record in self:
            record.total_sparepart_amount = sum(
                line.subtotal for line in record.sparepart_line_ids
            )
            record.total_service_amount = sum(
                line.subtotal for line in record.service_line_ids
            )
            on_risk_amount = sum(
                line.subtotal for line in record.on_risk_product_ids
            )
            record.total_amount = (
                record.total_sparepart_amount
                + record.total_service_amount
                + on_risk_amount
            )

    @api.depends("vehicle_id", "vehicle_id.model_year")
    def _compute_vehicle_snapshot(self):
        for record in self:
            record.year = record.vehicle_id.model_year if record.vehicle_id else False

    @api.depends("approval_tracking_ids.state", "approval_tracking_ids.approver_id", "state")
    def _compute_next_approver(self):
        for request in self:
            pending = request.approval_tracking_ids.filtered(
                lambda t: t.state == "pending"
            ).sorted(key=lambda t: (t.sequence, t.id))

            next_pending = pending[:1]
            request.next_approver_id = next_pending.approver_id if next_pending else False

    @api.depends("approval_tracking_ids.state", "approval_tracking_ids.approver_id",
                 "approval_tracking_ids.delegate_id", "state")
    def _compute_current_user_approval(self):
        current_user = self.env.user
        is_admin = current_user.has_group("base.group_system")
        today = fields.Date.context_today(self)

        for request in self:
            next_pending = request.approval_tracking_ids.filtered(
                lambda t: t.state == "pending"
            ).sorted(key=lambda t: (t.sequence, t.id))[:1]

            request.current_pending_approval_id = next_pending or False

            is_approver = next_pending and next_pending.approver_id == current_user
            is_valid_delegate = (
                next_pending
                and next_pending.delegate_id == current_user
                and next_pending._is_delegate_valid(today)
            )

            if request.state == "waiting_approval" and (is_approver or is_valid_delegate):
                request.can_current_user_approve = True
                request.current_user_approval_id = next_pending
            else:
                request.can_current_user_approve = False
                request.current_user_approval_id = False

            request.can_current_user_delegate = bool(
                request.state == "waiting_approval"
                and next_pending
                and (next_pending.approver_id == current_user or is_admin)
            )

    @api.onchange("vehicle_id")
    def _onchange_vehicle_id(self):
        for record in self:
            if record.vehicle_id:
                record.odometer = record.vehicle_id.odometer
                record.year = record.vehicle_id.model_year or ""
                record.last_service = record.vehicle_id.last_service

    @api.onchange("category")
    def _onchange_category(self):
        for record in self:
            if record.category != "internal":
                record.goods_issue_source_id = False

    def _check_required_fields(self):
        for record in self:
            if record.category == "internal" and not record.goods_issue_source_id:
                raise ValidationError(
                    "Goods Issue Source is required for internal category"
                )

    def _get_default_approver_user(self):
        """Return a fallback approver for unmapped approval chains (Edge Case 7.3)."""
        self.ensure_one()
        current_user = self.env.user
        if current_user.active and not current_user.share and current_user.login != "admin":
            return current_user

        return self.env["res.users"].search(
            [
                ("active", "=", True),
                ("share", "=", False),
                ("login", "!=", "admin"),
            ],
            order="id asc",
            limit=1,
        )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("name") or vals.get("name") == "/":
                vals["name"] = self.env["ir.sequence"].next_by_code("fleet.spk")

            vehicle_id = vals.get("vehicle_id")
            if vehicle_id:
                vehicle = self.env["fleet.vehicle"].browse(vehicle_id)
                if "odometer" not in vals or vals.get("odometer") in (False, None):
                    vals["odometer"] = vehicle.odometer
                if "last_service" not in vals:
                    vals["last_service"] = vehicle.last_service

        return super().create(vals_list)

    def write(self, vals):
        if "vehicle_id" in vals and vals.get("vehicle_id"):
            vehicle = self.env["fleet.vehicle"].browse(vals["vehicle_id"])
            vals.setdefault("odometer", vehicle.odometer)
            vals.setdefault("last_service", vehicle.last_service)

        return super().write(vals)

    def action_open_tyre_aki_wizard(self):
        for record in self:
            unfilled_tyres = record.tyre_detail_ids.filtered(
                lambda x: not x.old_production_number or not x.new_production_number
            )
            unfilled_akis = record.aki_detail_ids.filtered(
                lambda x: not x.old_AKI_code or not x.new_AKI_code
            )

            if not unfilled_tyres and not unfilled_akis:
                return {"type": "ir.actions.client", "tag": "display_notification", "params": {
                    "title": "Info",
                    "message": "All tyre and AKI details are already filled.",
                    "type": "info",
                }}

            tyre_lines = [(0, 0, {
                "tyre_line_id": tyre.id,
                "product_description": tyre.product_description,
                "old_production_number": tyre.old_production_number or "",
                "new_production_number": tyre.new_production_number or "",
                "notes": tyre.notes or "",
            }) for tyre in unfilled_tyres]

            aki_lines = [(0, 0, {
                "aki_line_id": aki.id,
                "product_description": aki.product_description,
                "old_AKI_code": aki.old_AKI_code or "",
                "new_AKI_code": aki.new_AKI_code or "",
                "notes": aki.notes or "",
            }) for aki in unfilled_akis]

            message_parts = []
            if tyre_lines:
                message_parts.append(
                    '<p style="font-size: 26px; margin: 0 0 8px 0;">There is a line item related to "Tyre", please input the details in the "Tyre Detail" tab</p>'
                )
            if aki_lines:
                message_parts.append(
                    '<p style="font-size: 26px; margin: 0 0 8px 0;">There is a line item related to "AKI", please input the details in the "AKI Detail" tab</p>'
                )

            wizard = self.env["spk.tyre.aki.wizard"].create({
                "spk_id": record.id,
                "tyre_detail_ids": tyre_lines,
                "aki_detail_ids": aki_lines,
                "message": "".join(message_parts),
            })

            return {
                "type": "ir.actions.act_window",
                "res_model": "spk.tyre.aki.wizard",
                "res_id": wizard.id,
                "view_mode": "form",
                "target": "new",
            }

    # =========================================================
    # STEP 1-4: Generate Approval Lines (Submit for Approval)
    # =========================================================

    def action_submit_for_approval(self):
        """Submit SPK for approval — triggers the full approval matrix flow."""
        self._check_required_fields()

        for record in self:
            # Validate tyre details
            tyre_required = record.sparepart_line_ids.filtered(lambda x: x.product_id.is_tyre)
            if tyre_required:
                unfilled = record.tyre_detail_ids.filtered(
                    lambda x: not x.old_production_number or not x.new_production_number
                )
                if unfilled:
                    raise ValidationError(
                        "All tyre old/new production numbers must be filled before submission"
                    )

            # Validate AKI details
            aki_required = record.sparepart_line_ids.filtered(lambda x: x.product_id.is_aki)
            if aki_required:
                unfilled = record.aki_detail_ids.filtered(
                    lambda x: not x.old_AKI_code or not x.new_AKI_code
                )
                if unfilled:
                    raise ValidationError(
                        "All AKI old/new codes must be filled before submission"
                    )

            # Validate SPK has amount (6.3)
            if not record.total_amount:
                raise ValidationError("SPK must have a total amount before submission.")

            record._generate_approval_lines()
            record.state = "waiting_approval"
            record._send_next_approver_notification(is_reminder=False)

    def _generate_approval_lines(self):
        """
        Core approval engine:
        Step 1 — Cancel existing pending approvals (re-submission support)
        Step 2 — Find applicable matrix by category + maintenance_type
        Step 3 — Fallback to default matrix if no specific match
        Step 4 — Filter lines by starting_amount threshold + date validity
        """
        self.ensure_one()

        # STEP 1: Cancel all pending approvals (audit history preserved)
        old_pending = self.approval_tracking_ids.filtered(lambda x: x.state == "pending")
        if old_pending:
            old_pending.write({
                "state": "cancelled",
                "date": fields.Datetime.now(),
            })

        # STEP 2: Find specific matrix
        matrix = self.env["spk.approval.matrix"].search([
            ("active", "=", True),
            ("is_default", "=", False),
            ("category", "=", self.category),
            ("maintenance_type_id", "=", self.maintenance_type_id.id),
        ], limit=1)

        # STEP 3: Fallback to default matrix
        if not matrix:
            matrix = self.env["spk.approval.matrix"].search([
                ("active", "=", True),
                ("is_default", "=", True),
                ("category", "=", self.category),
            ], limit=1)

        # Edge Case 7.1: No matrix found
        if not matrix:
            raise ValidationError(
                f"No approval matrix found for category '{self.category}'. "
                "Please configure an approval matrix."
            )

        # STEP 4: Filter lines — threshold logic (starting_amount) only
        # Main approver has no time restriction; only delegate validity is checked at approval time
        applicable_lines = matrix.approval_line_ids.filtered(
            lambda l: l.active and l.starting_amount <= self.total_amount
        ).sorted(key=lambda l: l.sequence)

        # Edge Case 7.2: No line matched
        if not applicable_lines:
            raise ValidationError(
                "No approval line matched for this SPK amount and date. "
                "Please review the approval matrix configuration."
            )

        # Create tracking records (snapshot — independent of matrix changes)
        for line in applicable_lines:
            approver = line.approver_id
            # Edge Case 7.3: Invalid approver → fallback
            if not approver or not approver.active or approver.share:
                approver = self._get_default_approver_user()
            if not approver:
                raise ValidationError("No valid approver found. Please configure a valid approver.")

            self.env["spk.approval.tracking"].create({
                "spk_id": self.id,
                "sequence": line.sequence,
                "approver_id": approver.id,
                "delegate_id": line.delegate_id.id if line.delegate_id else False,
                "delegate_valid_from": line.delegate_valid_from or False,
                "delegate_valid_to": line.delegate_valid_to or False,
                "state": "pending",
            })

    def _send_next_approver_notification(self, is_reminder=False):
        self.ensure_one()
        if self.state != "waiting_approval" or not self.next_approver_id:
            return

        message = (
            "Reminder: SPK %s is waiting your approval."
            if is_reminder
            else "SPK %s is waiting for your approval."
        ) % self.name

        self.activity_schedule(
            "mail.mail_activity_data_todo",
            user_id=self.next_approver_id.id,
            summary="SPK Approval",
            note=message,
        )
        self.message_post(body=message)

    # =========================================================
    # APPROVAL EXECUTION
    # =========================================================

    def _open_approval_action_wizard(self, action_type):
        self.ensure_one()
        if not self.can_current_user_approve or not self.current_user_approval_id:
            raise ValidationError(
                "You are not allowed to process this SPK at the current approval stage."
            )

        return {
            "type": "ir.actions.act_window",
            "name": "SPK Approval Action",
            "res_model": "spk.approval.action.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_spk_id": self.id,
                "default_approval_tracking_id": self.current_user_approval_id.id,
                "default_action_type": action_type,
            },
        }

    def action_open_accept_wizard(self):
        self.ensure_one()
        return self._open_approval_action_wizard("approve")

    def action_open_reject_wizard(self):
        self.ensure_one()
        return self._open_approval_action_wizard("reject")

    def action_approve(self):
        """Direct approve entry (bypasses wizard)."""
        for record in self:
            if not record.current_pending_approval_id:
                raise ValidationError("No pending approval stage found for this SPK.")
            record.current_pending_approval_id.action_approve()

    def action_reject(self):
        """Direct reject entry (bypasses wizard)."""
        for record in self:
            if not record.current_pending_approval_id:
                raise ValidationError("No pending approval stage found for this SPK.")
            record.current_pending_approval_id.action_reject()

    def action_done(self):
        self.state = "done"

    def action_received(self):
        self.state = "received"

    # =========================================================
    # POST-APPROVAL ACTIONS (triggered after all approvals done)
    # =========================================================

    def _post_approval_actions(self):
        """Execute all post-approval triggers after final approval."""
        for record in self:
            record._update_tyre_history()
            record._update_aki_history()
            if record.category == "external":
                record._create_purchase_order()
            elif record.category == "internal":
                record.action_trigger_internal_delivery()

    def _update_tyre_history(self):
        for record in self:
            for tyre_detail in record.tyre_detail_ids:
                self.env["fleet.vehicle.tyre.history"].create({
                    "vehicle_id": record.vehicle_id.id,
                    "spk_id": record.id,
                    "old_production_number": tyre_detail.old_production_number,
                    "new_production_number": tyre_detail.new_production_number,
                    "product_description": tyre_detail.product_description,
                    "notes": tyre_detail.notes,
                    "date": record.spk_date,
                })

    def _update_aki_history(self):
        for record in self:
            for aki_detail in record.aki_detail_ids:
                self.env["fleet.vehicle.aki.history"].create({
                    "vehicle_id": record.vehicle_id.id,
                    "spk_id": record.id,
                    "old_AKI_code": aki_detail.old_AKI_code,
                    "new_AKI_code": aki_detail.new_AKI_code,
                    "product_description": aki_detail.product_description,
                    "notes": aki_detail.notes,
                    "date": record.spk_date,
                })

    def _create_purchase_order(self):
        """Create a purchase order for external category SPK."""
        for record in self:
            if not record.vendor_id:
                raise ValidationError("Vendor must be selected for external SPK")

            po_lines = []
            for sparepart_line in record.sparepart_line_ids:
                product_variant = sparepart_line.product_id.product_variant_id
                po_lines.append((0, 0, {
                    "product_id": product_variant.id,
                    "product_qty": sparepart_line.quantity,
                    "price_unit": sparepart_line.unit_price,
                }))

            for service_line in record.service_line_ids:
                po_lines.append((0, 0, {
                    "product_id": service_line.product_id.id,
                    "product_qty": service_line.quantity,
                    "price_unit": service_line.unit_price,
                }))

            if po_lines:
                po = self.env["purchase.order"].create({
                    "partner_id": record.vendor_id.id,
                    "origin": record.name,
                    "order_line": po_lines,
                })
                record.po_id = po.id

    def action_trigger_internal_delivery(self):
        """Create a draft stock picking for internal goods issue."""
        for record in self:
            if not record.goods_issue_source_id:
                raise ValidationError(
                    "Goods Issue Source must be set before triggering internal delivery"
                )

            picking_type = record.goods_issue_source_id
            picking_lines = []
            for sparepart_line in record.sparepart_line_ids:
                product = sparepart_line.product_id
                product_variant = product.product_variant_id or product.product_variant_ids[0]
                picking_lines.append((0, 0, {
                    "product_id": product_variant.id,
                    "product_uom_qty": sparepart_line.quantity,
                    "product_uom": product.uom_id.id,
                }))

            if not picking_lines:
                return

            partner = record.vehicle_id.driver_id if hasattr(record.vehicle_id, "driver_id") else False
            picking = self.env["stock.picking"].sudo().create({
                "picking_type_id": picking_type.id,
                "partner_id": partner.id if partner else False,
                "origin": record.name,
                "move_ids": picking_lines,
            })

            record.message_post(
                body=f"Internal delivery picking created: {picking.name}",
                message_type="notification",
            )
