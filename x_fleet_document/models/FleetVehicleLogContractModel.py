from odoo import models, fields, api
from odoo.exceptions import ValidationError
import logging
_logger = logging.getLogger(__name__)

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

class FleetVehicleLogContract(models.Model):
    _inherit = 'fleet.vehicle.log.contract'

    ins_ref = fields.Char(string="Reference", required=True, help="Reference number for the insurance contract")
    cost_subtype_id = fields.Many2one('fleet.service.type', string="Type", required=True, help="Subtype of the cost associated with this contract")
    insurer_id = fields.Many2one('res.partner', string="Insurer", help="Insurance company providing coverage for the vehicle")
    user_id = fields.Many2one('res.users', string="Responsible", help="User responsible for this contract")
    vin_number = fields.Char(string="VIN Number", required=True, help="Vehicle Identification Number")
    license_plate = fields.Char(string="License Plate", required=True, help="Vehicle's license plate number")
    bpkb_location = fields.Char(string="BPKB Location", required=True, help="Location of the BPKB document")
    asset_number = fields.Char(string="Asset Number", required=True, help="Unique asset number for the vehicle")
    company_id = fields.Many2one('res.company', string="Company", required=True, default=lambda self: self.env.company, help="Company that owns the vehicle")

    line_ids = fields.One2many(
        'fleet.contract.product.line',
        'contract_id',
        string="Products"
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

    @api.onchange('license_plate')
    def _onchange_format_license_plate(self):
        for rec in self:
            if rec.license_plate:
                # Remove all non-alphanumeric characters for clean parsing
                clean = re.sub(r'[^a-zA-Z0-9]', '', rec.license_plate)
                match = re.match(r'^([A-Za-z]{1,2})(\d{1,4})([A-Za-z]{1,3})$', clean)
                if match:
                    # Auto format
                    rec.license_plate = f"{match.group(1).upper()} {match.group(2)} {match.group(3).upper()}"
                else:
                    # Just uppercase
                    rec.license_plate = rec.license_plate.upper()

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
