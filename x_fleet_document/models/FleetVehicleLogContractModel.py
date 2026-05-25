import re
import logging
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError, UserError
from odoo.tools.misc import format_date

_logger = logging.getLogger(__name__)

FLEET_CONTRACT_NOTIFICATION_SCOPE = 'fleet_contract'

_DEFAULT_FLEET_CONTRACT_EXPIRY_REMINDERS = (
    ('D60', 'H-60 hari', lambda end, today: end - timedelta(days=60) == today),
    ('D30', 'H-30 hari', lambda end, today: end - timedelta(days=30) == today),
    ('D14', 'H-14 hari', lambda end, today: end - timedelta(days=14) == today),
    ('D7', 'H-7 hari', lambda end, today: end - timedelta(days=7) == today),
)

class FleetVehicle(models.Model):
    _inherit = 'fleet.vehicle'

    analytic_account_id = fields.Many2one(
        'account.analytic.account',
        string="Analytic Account"
    )

    analytic_account_name = fields.Char(
        related='analytic_account_id.name',
        string='Analytic Account',
        store=True,
        readonly=True
    )

    running_fleet_document_id = fields.Many2one(
        'fleet.vehicle.log.contract',
        string='Running Fleet Document',
        compute='_compute_running_fleet_document_snapshot',
        store=True,
        readonly=True,
        help='Open fleet document used as master for plate, VIN, and asset number on other modules.',
    )
    fleet_document_license_plate = fields.Char(
        string='License Plate (Fleet Document)',
        compute='_compute_running_fleet_document_snapshot',
        store=True,
        readonly=True,
    )
    fleet_document_vin_number = fields.Char(
        string='VIN (Fleet Document)',
        compute='_compute_running_fleet_document_snapshot',
        store=True,
        readonly=True,
    )
    fleet_document_asset_number = fields.Char(
        string='Asset Number (Fleet Document)',
        compute='_compute_running_fleet_document_snapshot',
        store=True,
        readonly=True,
    )

    @api.depends(
        'log_contracts.state',
        'log_contracts.license_plate',
        'log_contracts.vin_number',
        'log_contracts.asset_number',
        'log_contracts.start_date',
        'license_plate',
        'vin_sn',
        'asset_number',
    )
    def _compute_running_fleet_document_snapshot(self):
        origin = fields.Date.from_string('1900-01-01')
        for vehicle in self:
            open_contracts = vehicle.log_contracts.filtered(lambda c: c.state == 'open')
            if open_contracts:
                contract = max(
                    open_contracts,
                    key=lambda c: ((c.start_date or origin), c.id),
                )
                vehicle.running_fleet_document_id = contract
                vehicle.fleet_document_license_plate = (
                    contract.license_plate or vehicle.license_plate or ''
                )
                vehicle.fleet_document_vin_number = (
                    contract.vin_number or vehicle.vin_sn or ''
                )
                vehicle.fleet_document_asset_number = (
                    contract.asset_number or vehicle.asset_number or ''
                )
            else:
                vehicle.running_fleet_document_id = False
                vehicle.fleet_document_license_plate = vehicle.license_plate or ''
                vehicle.fleet_document_vin_number = vehicle.vin_sn or ''
                vehicle.fleet_document_asset_number = vehicle.asset_number or ''

class FleetVehicleLogContract(models.Model):
    _inherit = 'fleet.vehicle.log.contract'

    ins_ref = fields.Char(string="Reference", required=False, help="Reference number for the insurance contract")
    cost_subtype_id = fields.Many2one('fleet.service.type', string="Type", required=True, help="Subtype of the cost associated with this contract")
    insurer_id = fields.Many2one('res.partner', string="Insurer", help="Insurance company providing coverage for the vehicle")
    user_id = fields.Many2one('res.users', string="Responsible", help="User responsible for this contract")
    vin_number = fields.Char(string="VIN Number", required=False, help="Vehicle Identification Number")
    license_plate = fields.Char(string="License Plate", required=False, help="Vehicle's license plate number")
    bpkb_location = fields.Char(string="BPKB Location", required=False, help="Location of the BPKB document")
    asset_number = fields.Char(string="Asset Number", required=False, help="Unique asset number for the vehicle")
    company_id = fields.Many2one('res.company', string="Company", required=True, default=lambda self: self.env.company, help="Company that owns the vehicle")

    line_ids = fields.One2many(
        'fleet.contract.product.line',
        'contract_id',
        string="Products"
    )

    vendor_id = fields.Many2one(
        'res.partner',
        string='Vendor'
    )

    vendor_bill_ids = fields.Many2many(
        'account.move',
        string='Vendor Bills',
        compute='_compute_vendor_bills'
    )
    vendor_bill_count = fields.Integer(
        string='Vendor Bills Count',
        compute='_compute_vendor_bills'
    )

    contract_expiry_reminder_stages_sent = fields.Char(
        string='Expiry reminder stages sent',
        copy=False,
        help='Comma-separated reminder stage keys already sent (see Notification template «End-date reminders»). '
             'Defaults match BASTK (D60, D30, D14, D7). Reset when Document Expiration Date changes.',
    )
    contract_expiry_send_label = fields.Char(
        string='Expiry reminder label (email render)',
        copy=False,
        help='Set only while sending CONTRACT email; use object.contract_expiry_send_label in mail body.',
    )
    contract_email_display_start = fields.Char(
        compute='_compute_contract_email_display_fields',
        string='Document start (email)',
    )
    contract_email_display_expiration = fields.Char(
        compute='_compute_contract_email_display_fields',
        string='Document expiration (email)',
    )
    contract_email_display_state = fields.Char(
        compute='_compute_contract_email_display_fields',
        string='Status (email)',
    )

    def _get_analytic_account_match_domain(self):
        """Match analytic row: company + plate; add asset_number when set (avoids broad False matches)."""
        self.ensure_one()
        domain = [
            ('license_plate', '=', self.license_plate),
            ('company_id', '=', self.company_id.id),
        ]
        vehicle = self.vehicle_id
        if vehicle and vehicle.asset_number:
            domain.append(('asset_number', '=', vehicle.asset_number))
        return domain

    def _apply_fleet_contract_auto_name(self):
        """Same naming rule as running-contract confirmation wizard."""
        self.ensure_one()
        contract = self
        model_name = (
            contract.vehicle_id.model_id.name
            if contract.vehicle_id and contract.vehicle_id.model_id
            else ''
        )
        manufacturer_name = (
            contract.vehicle_id.model_id.brand_id.name
            if contract.vehicle_id
            and contract.vehicle_id.model_id
            and contract.vehicle_id.model_id.brand_id
            else ''
        )
        license_plate = contract.license_plate or ''
        new_name = f"{contract.cost_subtype_id.name} {manufacturer_name}/{model_name}/{license_plate}"
        if contract.name != new_name:
            super(FleetVehicleLogContract, contract).write({'name': new_name})

    def _sync_vehicle_analytic_account_from_running_contract(self):
        """Create/update account.analytic.account for this open contract and link fleet.vehicle."""
        self.ensure_one()
        if not self.vehicle_id:
            raise ValidationError(_('Vehicle is required for analytic account sync.'))
        plan = self.env['account.analytic.plan'].search([], limit=1)
        if not plan:
            raise ValidationError(_('Analytic Plan not found.'))

        Analytic = self.env['account.analytic.account']
        existing = Analytic.search(self._get_analytic_account_match_domain(), limit=1)
        vals = {
            'name': f"{self.license_plate} - {self.vehicle_id.asset_number or ''}",
            'asset_number': self.vehicle_id.asset_number,
            'license_plate': self.license_plate,
            'partner_id': self.insurer_id.id,
            'code': self.ins_ref,
            'plan_id': plan.id,
            'company_id': self.company_id.id,
            'currency_id': self.currency_id.id,
        }
        if existing:
            existing.write(vals)
            self.vehicle_id.analytic_account_id = existing.id
        else:
            analytic = Analytic.create(vals)
            self.vehicle_id.analytic_account_id = analytic.id

        if self.cost_subtype_id.is_license_plate:
            self.vehicle_id.write({'license_plate': self.license_plate})

    def _fleet_raise_if_conflicting_running_document(self):
        """One open document per (vehicle, document type name); used when setting state to open."""
        for rec in self:
            existing = self.search(
                [
                    ("id", "!=", rec.id),
                    ("vehicle_id", "=", rec.vehicle_id.id),
                    ("cost_subtype_id.name", "=", rec.cost_subtype_id.name),
                    ("state", "=", "open"),
                ],
                limit=1,
            )
            if existing:
                raise ValidationError(
                    _(
                        "A document with type '%(type)s' is already running for this vehicle."
                    )
                    % {"type": rec.cost_subtype_id.name}
                )

    def write(self, vals):
        vals = dict(vals) if vals else {}
        if "expiration_date" in vals:
            vals["contract_expiry_reminder_stages_sent"] = False
            vals["contract_expiry_send_label"] = False

        # Statusbar (or any write) moving into Running: same hooks as the former confirm wizard.
        sync_analytic_ids = []
        if vals.get("state") == "open":
            opening = self.filtered(lambda r: r.state != "open")
            opening._fleet_raise_if_conflicting_running_document()
            for rec in opening:
                rec._apply_fleet_contract_auto_name()
            sync_analytic_ids = opening.ids

        if (
            "license_plate" in vals
            and not self.env.context.get("x_fleet_license_plate_wizard_ok")
        ):
            new_plate = vals["license_plate"]
            for rec in self:
                if rec.state != "open":
                    continue
                if (rec.license_plate or "") != (new_plate or ""):
                    raise UserError(
                        _(
                            "Cannot change the license plate on a running document from this screen. "
                            'Use the "Change license plate" button and confirm in the wizard '
                            "(a new analytic account will be created or updated for the new plate)."
                        )
                    )

        res = super().write(vals)

        if sync_analytic_ids:
            for rec in self.browse(sync_analytic_ids).filtered(lambda r: r.state == "open"):
                rec._sync_vehicle_analytic_account_from_running_contract()

        return res

    @api.depends('start_date', 'expiration_date', 'state')
    def _compute_contract_email_display_fields(self):
        state_labels = dict(self._fields['state'].selection)
        for rec in self:
            rec.contract_email_display_start = (
                format_date(rec.env, rec.start_date) if rec.start_date else ''
            )
            rec.contract_email_display_expiration = (
                format_date(rec.env, rec.expiration_date) if rec.expiration_date else ''
            )
            rec.contract_email_display_state = (
                state_labels.get(rec.state, rec.state or '') or ''
            )

    @api.model
    def _fleet_contract_active_reminder_schedule(self):
        """Use reminder lines on the active «Use for = Fleet contract» template, else BASTK-style default."""
        Notif = self.env['x.notification.template'].sudo()
        template = Notif.get_template_for_scope_model(
            FLEET_CONTRACT_NOTIFICATION_SCOPE,
            'fleet.vehicle.log.contract',
        )
        if template and template.reminder_line_ids:
            return template.iter_end_date_reminder_checks()
        return list(_DEFAULT_FLEET_CONTRACT_EXPIRY_REMINDERS)

    def _get_contract_expiry_stages_sent(self):
        self.ensure_one()
        if not self.contract_expiry_reminder_stages_sent:
            return set()
        return {
            x.strip()
            for x in self.contract_expiry_reminder_stages_sent.split(',')
            if x.strip()
        }

    def _contract_notification_email_values(self):
        """Build recipients: insurer first, then responsible user (fleet.user_id)."""
        self.ensure_one()
        candidates = []
        if self.insurer_id:
            candidates.append(self.insurer_id)
        if self.user_id and self.user_id.partner_id:
            if not self.insurer_id or self.user_id.partner_id.id != self.insurer_id.id:
                candidates.append(self.user_id.partner_id)

        for partner in candidates:
            if partner.email:
                return {
                    'email_to': partner.email_formatted,
                    'recipient_ids': [(6, 0, [partner.id])],
                }

        _logger.warning(
            'Contract %s (%s): insurer / responsible partner has no email; '
            'cannot send CONTRACT notification.',
            self.id,
            self.display_name or '',
        )
        return None

    def _contract_send_expiry_notify(self, stage_key, stage_label):
        self.ensure_one()
        template_context = {
            'contract_reminder_stage': stage_key,
            'contract_reminder_label': stage_label,
        }
        email_values = self._contract_notification_email_values()
        if not email_values:
            return False

        self.write({'contract_expiry_send_label': stage_label})
        try:
            self.env['x.notification.template'].sudo().send_notification_for_scope(
                self,
                FLEET_CONTRACT_NOTIFICATION_SCOPE,
                template_context=template_context,
                email_values=email_values,
            )
            return True
        except UserError as err:
            _logger.warning(
                'Fleet document expiry reminder skipped (record %s, stage %s): %s',
                self.id, stage_key, err,
            )
            return False
        finally:
            self.write({'contract_expiry_send_label': False})

    @api.model
    def cron_send_contract_expiration_notifications(self):
        """Daily: fleet document expiry emails via Notification template «Use for = Fleet contract».

        Schedule from template «End-date reminders» when configured; otherwise same defaults as BASTK
        (H-60 / H-30 / H-14 / H-7 calendar days before expiration_date).

        Mail subject may use {{ }}; body QWeb must use simple t-out paths only
        (e.g. object.contract_expiry_send_label, object.contract_email_display_expiration).
        """
        reminders = self._fleet_contract_active_reminder_schedule()
        today = fields.Date.today()
        candidates = self.search([
            ('expiration_date', '!=', False),
            ('state', '=', 'open'),
        ])
        for rec in candidates:
            exp = rec.expiration_date
            if exp < today:
                continue
            sent = rec._get_contract_expiry_stages_sent()
            new_stages = []
            for stage_key, stage_label, predicate in reminders:
                if stage_key in sent:
                    continue
                if not predicate(exp, today):
                    continue
                if rec._contract_send_expiry_notify(stage_key, stage_label):
                    new_stages.append(stage_key)
            if new_stages:
                rec.contract_expiry_reminder_stages_sent = ','.join(
                    sorted(sent | set(new_stages))
                )

    vendor_id = fields.Many2one(
        'res.partner',
        string='Vendor'
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            # Selalu paksa state = 'futur' (New) saat dokumen baru dibuat
            vals['state'] = 'futur'

            vehicle_id = vals.get('vehicle_id')
            subtype_id = vals.get('cost_subtype_id')

            # Hanya cek duplikat jika keduanya sudah diisi
            if vehicle_id and subtype_id:
                subtype = self.env['fleet.service.type'].browse(subtype_id)
                existing = self.search([
                    ('vehicle_id', '=', vehicle_id),
                    ('cost_subtype_id.name', '=', subtype.name),
                    ('state', '=', 'open')
                ], limit=1)
                if existing:
                    raise ValidationError(
                        f"A document with type '{subtype.name}' is already running for this vehicle"
                    )

        return super().create(vals_list)
    
    @api.onchange('vehicle_id')
    def _onchange_vehicle_id(self):
        if self.vehicle_id:
            self.state = 'futur'
            v = self.vehicle_id
            # Auto-fill dari data kendaraan
            self.license_plate = v.license_plate or ''
            # VIN: pakai vin_sn dari base fleet, atau chassis_number jika ada
            self.vin_number = (
                getattr(v, 'chassis_number', None)
                or v.vin_sn
                or ''
            )
            self.asset_number = getattr(v, 'asset_number', None) or ''
        else:
            self.license_plate = False
            self.vin_number = False
            self.asset_number = False

    @api.model
    def format_license_plate_input(self, value):
        """Normalize license plate (same rules as onchange on the contract)."""
        if not value:
            return value
        value = value.strip()
        clean = re.sub(r'[^a-zA-Z0-9]', '', value)
        match = re.match(r'^([A-Za-z]{1,2})(\d{1,4})([A-Za-z]{0,3})$', clean)
        if match:
            return f"{match.group(1).upper()} {match.group(2)} {match.group(3).upper()}".strip()
        return value.upper()

    @api.onchange('license_plate')
    def _onchange_format_license_plate(self):
        for rec in self:
            if rec.license_plate:
                # Remove all non-alphanumeric characters for clean parsing
                clean = re.sub(r'[^a-zA-Z0-9]', '', rec.license_plate)
                match = re.match(r'^([A-Za-z]{1,2})(\d{1,4})([A-Za-z]{0,3})$', clean)
                if match:
                    # Auto format
                    rec.license_plate = f"{match.group(1).upper()} {match.group(2)} {match.group(3).upper()}".strip()
                else:
                    # Just uppercase
                    rec.license_plate = rec.license_plate.upper()

    @api.constrains('license_plate')
    def _check_license_plate_format(self):
        pattern = r'^[A-Za-z]{1,2}\s*\d{1,4}\s*[A-Za-z]{0,3}$'
        for rec in self:
            if rec.license_plate:
                if not re.match(pattern, rec.license_plate):
                    raise ValidationError(
                        "Invalid License Plate Format!\n"
                        "Correct Format: [1-2 Letters] [1-4 Numbers] [0-3 Letters]\n"
                        "Example: 'B 1234', 'AB 12', or 'B 1234 CD'"
                    )

    def action_open_change_license_plate_wizard(self):
        self.ensure_one()
        if self.state != 'open':
            raise UserError(
                _('You can only change the license plate with the wizard when the document is running.')
            )
        return {
            'type': 'ir.actions.act_window',
            'name': _('Change license plate'),
            'res_model': 'fleet.contract.change.plate.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_contract_id': self.id,
            },
        }

    def action_set_running(self):
        """Optional confirmation popup; transition to open uses write() (naming + analytic sync)."""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "Confirmation",
            "res_model": "fleet.contract.confirm.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_contract_id": self.id},
        }

    def action_set_draft(self):
        self.write({"state": "futur"})

    def action_set_expired(self):
        self.write({"state": "expired"})

    def action_set_cancel(self):
        for rec in self:
            rec.state = 'closed'

    def _compute_vendor_bills(self):
        for rec in self:
            bills = self.env['account.move'].search([
                ('move_type', '=', 'in_invoice'),
                ('x_fleet_contract_ids', 'in', rec.id)
            ])
            rec.vendor_bill_ids = bills
            rec.vendor_bill_count = len(bills)

    def action_view_vendor_bills(self):
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id("account.action_move_in_invoice_type")
        bills = self.vendor_bill_ids
        if len(bills) == 1:
            action['views'] = [(self.env.ref('account.view_move_form').id, 'form')]
            action['res_id'] = bills.id
        else:
            action['domain'] = [('id', 'in', bills.ids)]
        return action

    def action_create_vendor_bill(self):
        self.ensure_one()

        if not self.vendor_id:
            raise ValidationError("Vendor harus diisi terlebih dahulu.")

        invoice_lines = []
        selected_lines = self.line_ids.filtered(lambda l: l.selected)

        if not selected_lines:
            raise ValidationError("Pilih minimal 1 product.")

        for line in selected_lines:
            line_vals = {
                'product_id': line.product_id.id,
                'quantity': line.quantity,
                'price_unit': line.product_id.standard_price,
                'name': line.product_id.name,
            }
            if line.analytic_account_id:
                line_vals['analytic_distribution'] = {str(line.analytic_account_id.id): 100}
            invoice_lines.append((0, 0, line_vals))

        bill = self.env['account.move'].create({
            'move_type': 'in_invoice',
            'partner_id': self.vendor_id.id,
            'invoice_line_ids': invoice_lines,
            'x_fleet_contract_ids': [(4, self.id)],
        })

        self.message_post(body="Vendor Bill Created")

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'res_id': bill.id,
            'view_mode': 'form',
        }
    
    def action_create_vendor_bill_multi(self):
        invoice_lines = []
        vendors = self.mapped('vendor_id')

        if len(vendors) > 1:
            raise ValidationError(
                "Vendor harus sama untuk multi vendor bill."
            )

        for rec in self:
            if not rec.vendor_id:
                continue

            selected_lines = rec.line_ids.filtered(
                lambda l: l.selected
            )

            for line in selected_lines:
                line_vals = {
                    'product_id': line.product_id.id,
                    'quantity': line.quantity,
                    'price_unit': line.product_id.standard_price,
                    'name': f"{rec.name} - {line.product_id.name}",
                }
                if line.analytic_account_id:
                    line_vals['analytic_distribution'] = {str(line.analytic_account_id.id): 100}
                invoice_lines.append((0, 0, line_vals))

        if not invoice_lines:
            raise ValidationError(
                "Tidak ada product yang dipilih."
            )

        bill = self.env['account.move'].create({
            'move_type': 'in_invoice',
            'partner_id': vendors.id,
            'invoice_line_ids': invoice_lines,
            'x_fleet_contract_ids': [(6, 0, self.ids)],
        })

        for rec in self:
            rec.message_post(
                body="Vendor Bill Created"
            )

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'res_id': bill.id,
            'view_mode': 'form',
        }

