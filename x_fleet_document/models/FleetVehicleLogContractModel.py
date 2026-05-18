import re
import logging
from datetime import timedelta

from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError, UserError
from odoo.tools.misc import format_date

_logger = logging.getLogger(__name__)

FLEET_CONTRACT_NOTIFICATION_SCOPE = 'fleet_contract'

_CONTRACT_EXPIRY_REMINDERS = (
    ('2M', 'H-2 bulan', lambda exp, today: exp - relativedelta(months=2) == today),
    ('1M', 'H-1 bulan', lambda exp, today: exp - relativedelta(months=1) == today),
    ('14D', 'H-14 hari', lambda exp, today: exp - timedelta(days=14) == today),
    ('7D', 'H-7 hari', lambda exp, today: exp - timedelta(days=7) == today),
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

    ins_ref = fields.Char(string="Reference", required=True, help="Reference number for the insurance contract")
    cost_subtype_id = fields.Many2one('fleet.service.type', string="Type", required=True, help="Subtype of the cost associated with this contract")
    insurer_id = fields.Many2one('res.partner', string="Insurer", help="Insurance company providing coverage for the vehicle")
    user_id = fields.Many2one('res.users', string="Responsible", help="User responsible for this contract")
    vin_number = fields.Char(string="VIN Number", required=True, help="Vehicle Identification Number")
    license_plate = fields.Char(string="License Plate", required=True, help="Vehicle's license plate number")
    bpkb_location = fields.Char(string="BPKB Location", required=True, help="Location of the BPKB document")
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

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            # vals['state'] = 'futur'
            # _logger.info(f"Creating contract with values: {vals}")

            if vals.get('state') == 'futur':

                vehicle_id = vals.get('vehicle_id')
                subtype_id = vals.get('cost_subtype_id')

                if vehicle_id and subtype_id:
                    subtype = self.env['fleet.service.type'].browse(subtype_id)

                    existing = self.search([
                        ('vehicle_id', '=', vehicle_id),
                        ('cost_subtype_id.name', '=', subtype.name),
                        ('state', '=', 'open')
                    ], limit=1)

                    if existing:
                        raise ValidationError(f"A document with type '{subtype.name}' is already running for this vehicle")
                else:
                    raise ValidationError("Please complete all required fields.")

        return super().create(vals_list)
    
    @api.onchange('vehicle_id')
    def _onchange_vehicle_id(self):
        if self.vehicle_id:
            self.state = 'futur'
    
        for rec in self:
            if rec.vehicle_id:
                rec.license_plate = rec.vehicle_id.license_plate
            else:
                rec.license_plate = False

    @api.model
    def format_license_plate_input(self, value):
        """Normalize license plate (same rules as onchange on the contract)."""
        if not value:
            return value
        value = value.strip()
        clean = re.sub(r'[^a-zA-Z0-9]', '', value)
        match = re.match(r'^([A-Za-z]{1,2})(\d{1,4})([A-Za-z]{1,3})$', clean)
        if match:
            return f"{match.group(1).upper()} {match.group(2)} {match.group(3).upper()}"
        return value.upper()

    @api.onchange('license_plate')
    def _onchange_format_license_plate(self):
        for rec in self:
            if rec.license_plate:
                rec.license_plate = self.format_license_plate_input(rec.license_plate)

    @api.constrains('license_plate')
    def _check_license_plate_format(self):
        pattern = r'^[A-Za-z]{1,2}\s*\d{1,4}\s*[A-Za-z]{1,3}$'
        for rec in self:
            if rec.license_plate:
                if not re.match(pattern, rec.license_plate):
                    raise ValidationError(
                        "Format License Plate tidak valid!\n"
                        "Format yang benar: [1-2 Huruf] [1-4 Angka] [1-3 Huruf]\n"
                        "Contoh: 'B 1234 ABC' atau 'AB 1 CD'"
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
        self.ensure_one()

        existing = self.search([
            ('id', '!=', self.id),
            ('vehicle_id', '=', self.vehicle_id.id),
            ('cost_subtype_id.name', '=', self.cost_subtype_id.name),
            ('state', '=', 'open')
        ], limit=1)

        if existing:
            raise ValidationError(
                f"A document with type '{self.cost_subtype_id.name}' is already running for this vehicle"
            )

        return {
            'type': 'ir.actions.act_window',
            'name': 'Confirmation',
            'res_model': 'fleet.contract.confirm.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_contract_id': self.id
            }
        }
    
    def action_set_draft(self):
        for rec in self:
            rec.state = 'futur'

    def action_set_expired(self):
        for rec in self:
            rec.state = 'expired'

    def action_set_cancel(self):
        for rec in self:
            rec.state = 'closed'

    def action_create_vendor_bill(self):
        self.ensure_one()

        if not self.vendor_id:
            raise ValidationError("Vendor harus diisi terlebih dahulu.")

        invoice_lines = []

        selected_lines = self.line_ids.filtered(lambda l: l.selected)

        if not selected_lines:
            raise ValidationError("Pilih minimal 1 product.")

        for line in selected_lines:
            invoice_lines.append((0, 0, {
                'product_id': line.product_id.id,
                'quantity': line.quantity,
                'price_unit': line.product_id.standard_price,
                'name': line.product_id.name,
            }))

        bill = self.env['account.move'].create({
            'move_type': 'in_invoice',
            'partner_id': self.vendor_id.id,
            'invoice_line_ids': invoice_lines,
        })

        self.message_post(body="Vendor Bill Created")

        selected_lines.write({
            'selected': False
        })

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'res_id': bill.id,
            'view_mode': 'form',
        }