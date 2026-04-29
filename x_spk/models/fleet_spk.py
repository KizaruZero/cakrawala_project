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
            ("draft", "Draft"),
            ("waiting_approval", "Waiting Approval"),
            ("approved", "Approved"),
            ("done", "Done"),
            ("rejected", "Rejected"),
            ("closed", "SPK Closed"),
        ],
        string="State",
        default="draft",
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
        help="BAK (Berita Acara Kendaraan) form reference number. Will be linked to BAK module when available.",
    )
    bak_reference = fields.Char(
        string="BAK Reference",
    )

    goods_issue_source_id = fields.Many2one(
        "stock.picking.type",
        string="Goods Issue Source",
        domain="[('code', '=', 'internal')]",
    )
    goods_issue_source_text = fields.Char(
        string="Goods Issue Source",
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
    approval_line_ids = fields.One2many(
        "spk.approval.line",
        "spk_id",
        string="Approvals",
    )
    next_approver_id = fields.Many2one(
        "res.users",
        string="Current Approver",
        compute="_compute_next_approver",
        store=True,
        tracking=True,
    )
    approver_stage = fields.Selection(
        [
            ("none", "No Stage"),
            ("l1", "Manager Stage"),
            ("l2", "Senior Manager Stage"),
            ("l3", "Director Stage"),
            ("done", "Completed"),
        ],
        string="Approval Stage",
        compute="_compute_next_approver",
        store=True,
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
        "spk.approval.line",
        string="Current User Approval",
        compute="_compute_current_user_approval",
    )
    current_pending_approval_id = fields.Many2one(
        "spk.approval.line",
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

    def _compute_totals(self):
        for record in self:
            record.total_sparepart_amount = sum(
                line.subtotal for line in record.sparepart_line_ids
            )
            record.total_service_amount = sum(
                line.subtotal for line in record.service_line_ids
            )
            record.total_amount = (
                record.total_sparepart_amount + record.total_service_amount
            )

    @api.depends("vehicle_id", "vehicle_id.model_year")
    def _compute_vehicle_snapshot(self):
        for record in self:
            record.year = record.vehicle_id.model_year if record.vehicle_id else False

    @api.depends("approval_line_ids.state", "approval_line_ids.role", "approval_line_ids.approver_id", "state")
    def _compute_next_approver(self):
        role_order = {"l1": 1, "l2": 2, "l3": 3}
        for request in self:
            pending_approvers = request.approval_line_ids.filtered(
                lambda approver: approver.state == "pending"
            ).sorted(key=lambda approver: (role_order.get(approver.role, 99), approver.sequence, approver.id))

            next_approver = pending_approvers[:1]
            request.next_approver_id = next_approver.approver_id if next_approver else False

            if request.state == "approved":
                request.approver_stage = "done"
            elif next_approver:
                request.approver_stage = next_approver.role
            else:
                request.approver_stage = "none"

    @api.depends("approval_line_ids.state", "approval_line_ids.role", "approval_line_ids.approver_id", "state")
    def _compute_current_user_approval(self):
        role_order = {"l1": 1, "l2": 2, "l3": 3}
        current_user = self.env.user
        is_admin = current_user.has_group("base.group_system")
        for request in self:
            next_pending = request.approval_line_ids.filtered(
                lambda approver: approver.state == "pending"
            ).sorted(key=lambda approver: (role_order.get(approver.role, 99), approver.sequence, approver.id))[:1]

            request.current_pending_approval_id = next_pending or False

            if request.state == "waiting_approval" and next_pending and next_pending.approver_id == current_user:
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
        """Auto-fill odometer and year from selected vehicle."""
        for record in self:
            if record.vehicle_id:
                record.odometer = record.vehicle_id.odometer
                record.year = record.vehicle_id.model_year or ""
                record.last_service = record.vehicle_id.last_service

    @api.onchange("category")
    def _onchange_category(self):
        """Reset goods_issue_source when category changes."""
        for record in self:
            if record.category != "internal":
                record.goods_issue_source_id = False

    def _check_required_fields(self):
        """Validate required fields based on current state."""
        for record in self:
            # Goods Issue Source required if category is internal
            if record.category == "internal" and not record.goods_issue_source_id:
                raise ValidationError(
                    "Goods Issue Source is required for internal category"
                )

    def _get_default_approver_user(self):
        """Return a relaxed fallback approver for matrix-less or unmapped approval chains."""
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
        # Auto-generate SPK number using sequence for each created record
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
        """Open wizard to fill tyre and AKI details."""

        for record in self:
            # Get unfilled tyre details
            unfilled_tyres = record.tyre_detail_ids.filtered(
                lambda x: not x.old_production_number or not x.new_production_number
            )
            
            # Get unfilled aki details
            unfilled_akis = record.aki_detail_ids.filtered(
                lambda x: not x.old_AKI_code or not x.new_AKI_code
            )
            
            if not unfilled_tyres and not unfilled_akis:
                return {"type": "ir.actions.client", "tag": "display_notification", "params": {
                    "title": "Info",
                    "message": "All tyre and AKI details are already filled.",
                    "type": "info",
                }}
            
            # Create wizard lines for tyres
            tyre_lines = []
            for tyre in unfilled_tyres:
                tyre_lines.append((0, 0, {
                    "tyre_line_id": tyre.id,
                    "product_description": tyre.product_description,
                    "old_production_number": tyre.old_production_number or "",
                    "new_production_number": tyre.new_production_number or "",
                    "notes": tyre.notes or "",
                }))
            
            # Create wizard lines for AKIs
            aki_lines = []
            for aki in unfilled_akis:
                aki_lines.append((0, 0, {
                    "aki_line_id": aki.id,
                    "product_description": aki.product_description,
                    "old_AKI_code": aki.old_AKI_code or "",
                    "new_AKI_code": aki.new_AKI_code or "",
                    "notes": aki.notes or "",
                }))
            
            # Create warning message
            message_parts = []
            if tyre_lines:
                message_parts.append(
                    '<p style="font-size: 26px; margin: 0 0 8px 0;">There is a line item related to "Tyre", please input the details in the "Tyre Detail" tab</p>'
                )
            if aki_lines:
                message_parts.append(
                    '<p style="font-size: 26px; margin: 0 0 8px 0;">There is a line item related to "AKI", please input the details in the "AKI Detail" tab</p>'
                )
            wizard_msg = "".join(message_parts)
            
            wizard = self.env["spk.tyre.aki.wizard"].create({
                "spk_id": record.id,
                "tyre_detail_ids": tyre_lines,
                "aki_detail_ids": aki_lines,
                "message": wizard_msg,
            })
            
            # Return action to open wizard
            return {
                "type": "ir.actions.act_window",
                "res_model": "spk.tyre.aki.wizard",
                "res_id": wizard.id,
                "view_mode": "form",
                "target": "new",
            }

    def action_submit_for_approval(self):
        """Submit SPK for approval."""
        # Validate all required fields
        self._check_required_fields()
        
        # Check if tyre/aki details are filled if applicable
        for record in self:
            tyre_required = record.sparepart_line_ids.filtered(
                lambda x: x.product_id.is_tyre
            )
            if tyre_required:
                unfilled = record.tyre_detail_ids.filtered(
                    lambda x: not x.old_production_number or not x.new_production_number
                )
                if unfilled:
                    raise ValidationError(
                        "All tyre old/new production numbers must be filled before submission"
                    )

            aki_required = record.sparepart_line_ids.filtered(
                lambda x: x.product_id.is_aki
            )
            if aki_required:
                unfilled = record.aki_detail_ids.filtered(
                    lambda x: not x.old_AKI_code or not x.new_AKI_code
                )
                if unfilled:
                    raise ValidationError(
                        "All AKI old/new codes must be filled before submission"
                    )

            record._generate_approval_lines()
            record.state = "waiting_approval"
            record._send_next_approver_notification(is_reminder=False)

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
                "default_approval_id": self.current_user_approval_id.id,
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
        """Backward-compatible approve action entry."""
        for record in self:
            if not record.current_pending_approval_id:
                raise ValidationError("No pending approval stage found for this SPK.")
            record.current_pending_approval_id.action_approve()

    def action_reject(self):
        """Backward-compatible reject action entry."""
        for record in self:
            if not record.current_pending_approval_id:
                raise ValidationError("No pending approval stage found for this SPK.")
            record.current_pending_approval_id.action_reject()

    def action_done(self):
        """Mark SPK as Done."""
        self.state = "done"

    def action_close(self):
        """Mark SPK as Closed."""
        self.state = "closed"

    def _generate_approval_lines(self):
        """Auto-generate approval lines from active matrix based on SPK context.
        
        Tries to match specific matrix (category + maintenance_type + amount range).
        Falls back to default rule if no specific match found.
        """
        self.ensure_one()

        # Cancel previous pending approvals if record is re-submitted
        old_pending = self.approval_line_ids.filtered(lambda x: x.state == "pending")
        if old_pending:
            old_pending.with_context(skip_approval_write_check=True).write(
                {
                    "state": "cancelled",
                    "action_date": fields.Datetime.now(),
                }
            )

        # First, try to find specific matrix matching category, type, and amount
        matrix = self.env["spk.approval.matrix"].search(
            [
                ("active", "=", True),
                ("is_default", "=", False),
                ("category", "=", self.category),
                ("maintenance_type_id", "=", self.maintenance_type_id.id),
                ("amount_from", "<=", self.total_amount),
                ("amount_to", ">=", self.total_amount),
            ],
            order="id desc",
            limit=1,
        )

        # If no specific match, try default rule for this category
        if not matrix:
            matrix = self.env["spk.approval.matrix"].search(
                [
                    ("active", "=", True),
                    ("is_default", "=", True),
                    ("category", "=", self.category),
                ],
                limit=1,
            )

        approval_vals = []
        next_cycle = (max(self.approval_line_ids.mapped("approval_cycle")) if self.approval_line_ids else 0) + 1
        
        if matrix:
            for line in matrix.approval_line_ids.sorted(key=lambda l: l.sequence):
                # Get approver from role mapping
                approver = line.approval_role_id.user_id if line.approval_role_id else None
                
                if not approver or not approver.active or approver.share or approver.login == "admin":
                    # Fallback to first active internal user if role mapping not available
                    approver = self._get_default_approver_user()
                
                if not approver:
                    raise ValidationError(
                        "No active approver found for role '%s' and no fallback user is available."
                        % (line.approval_role_id.display_name if line.approval_role_id else "Unknown")
                    )
                
                # Derive approval role from sequence for backward compatibility
                role_map = {1: "l1", 2: "l2", 3: "l3"}
                approval_role = role_map.get(line.approval_role_id.sequence, "l1")
                
                approval_vals.append(
                    (
                        0,
                        0,
                        {
                            "sequence": line.sequence,
                            "approver_id": approver.id,
                            "role": approval_role,
                            "state": "pending",
                            "approval_cycle": next_cycle,
                        },
                    )
                )

        if not approval_vals:
            # Fallback to current user if no matrix found
            default_approver = self.env.user
            if not default_approver.active or default_approver.share or default_approver.login == "admin":
                default_approver = self.env["res.users"].search(
                    [
                        ("active", "=", True),
                        ("share", "=", False),
                        ("login", "!=", "admin"),
                    ],
                    order="id asc",
                    limit=1,
                )

            if not default_approver:
                raise ValidationError(
                    "No default approver available. Please configure approval matrix or activate at least one internal user."
                )

            approval_vals = [
                (
                    0,
                    0,
                    {
                        "sequence": 1,
                        "approver_id": default_approver.id,
                        "role": "l1",
                        "state": "pending",
                        "approval_cycle": next_cycle,
                    },
                )
            ]

        self.write({"approval_line_ids": approval_vals})

    def _send_next_approver_notification(self, is_reminder=False):
        self.ensure_one()
        if self.state != "waiting_approval":
            return

        if not self.next_approver_id:
            return

        message = (
            "Reminder: SPK %s is waiting your approval."
            if is_reminder
            else "SPK %s is waiting your approval."
        ) % self.name

        self.activity_schedule(
            "mail.mail_activity_data_todo",
            user_id=self.next_approver_id.id,
            summary="SPK Approval",
            note=message,
        )
        self.message_post(body=message)

    def _post_approval_actions(self):
        """Execute all post-approval triggers."""
        for record in self:
            # Update tyre history in fleet.vehicle
            record._update_tyre_history()
            # Update AKI history in fleet.vehicle
            record._update_aki_history()
            # Create PO for external category
            if record.category == "external":
                record._create_purchase_order()
            # Call the internal delivery method
            elif record.category == "internal":
                record.action_trigger_internal_delivery()

    def _update_tyre_history(self):
        """Write tyre details to fleet vehicle history."""
        for record in self:
            for tyre_detail in record.tyre_detail_ids:
                self.env["fleet.vehicle.tyre.history"].create(
                    {
                        "vehicle_id": record.vehicle_id.id,
                        "spk_id": record.id,
                        "old_production_number": tyre_detail.old_production_number,
                        "new_production_number": tyre_detail.new_production_number,
                        "product_description": tyre_detail.product_description,
                        "notes": tyre_detail.notes,
                        "date": record.spk_date,
                    }
                )

    def _update_aki_history(self):
        """Write AKI details to fleet vehicle history."""
        for record in self:
            for aki_detail in record.aki_detail_ids:
                self.env["fleet.vehicle.aki.history"].create(
                    {
                        "vehicle_id": record.vehicle_id.id,
                        "spk_id": record.id,
                        "old_AKI_code": aki_detail.old_AKI_code,
                        "new_AKI_code": aki_detail.new_AKI_code,
                        "product_description": aki_detail.product_description,
                        "notes": aki_detail.notes,
                        "date": record.spk_date,
                    }
                )

    def _create_purchase_order(self):
        """Create a purchase order for external category SPK."""
        for record in self:
            if not record.vendor_id:
                raise ValueError("Vendor must be selected for external SPK")

            po_lines = []
            # Add sparepart lines
            for sparepart_line in record.sparepart_line_ids:
                product_variant = sparepart_line.product_id.product_variant_id
                po_lines.append(
                    (
                        0,
                        0,
                        {
                            "product_id": product_variant.id,
                            "product_qty": sparepart_line.quantity,
                            "price_unit": sparepart_line.unit_price,
                        },
                    )
                )

            # Add service lines
            for service_line in record.service_line_ids:
                po_lines.append(
                    (
                        0,
                        0,
                        {
                            "product_id": service_line.product_id.id,
                            "product_qty": service_line.quantity,
                            "price_unit": service_line.unit_price,
                        },
                    )
                )

            if po_lines:
                po = self.env["purchase.order"].create(
                    {
                        "partner_id": record.vendor_id.id,
                        "origin": record.name,
                        "order_line": po_lines,
                    }
                )
                record.po_id = po.id

    def action_trigger_internal_delivery(self):
        """
        Trigger internal delivery workflow.
        Create a draft stock picking for internal goods issue.
        """
        for record in self:
            if not record.goods_issue_source_id:
                raise ValidationError(
                    "Goods Issue Source must be set before triggering internal delivery"
                )

            picking_type = record.goods_issue_source_id
            
            # Build picking lines from sparepart items
            picking_lines = []
            for sparepart_line in record.sparepart_line_ids:
                product = sparepart_line.product_id
                product_variant = product.product_variant_id or product.product_variant_ids[0]
                
                picking_lines.append(
                    (
                        0,
                        0,
                        {
                            "product_id": product_variant.id,
                            "product_uom_qty": sparepart_line.quantity,
                            "product_uom": product.uom_id.id,
                        },
                    )
                )

            if not picking_lines:
                return  # No items to deliver

            # Create draft stock picking
            partner = record.vehicle_id.driver_id if hasattr(record.vehicle_id, "driver_id") else False
            picking = self.env["stock.picking"].sudo().create(
                {
                    "picking_type_id": picking_type.id,
                    "partner_id": partner.id if partner else False,
                    "origin": record.name,
                    "move_ids": picking_lines,
                }
            )
            
            record.message_post(
                body=f"Internal delivery picking created: {picking.name}",
                message_type="notification",
            )
