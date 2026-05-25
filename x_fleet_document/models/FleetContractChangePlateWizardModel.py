import re

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class FleetContractChangePlateWizard(models.TransientModel):
    _name = 'fleet.contract.change.plate.wizard'
    _description = 'Confirm license plate change (running fleet document)'

    contract_id = fields.Many2one(
        'fleet.vehicle.log.contract',
        string='Document',
        required=True,
        ondelete='cascade',
    )
    current_license_plate = fields.Char(
        related='contract_id.license_plate',
        string='Current license plate',
        readonly=True,
    )
    new_license_plate = fields.Char(string='New license plate', required=True)

    @api.onchange('new_license_plate')
    def _onchange_new_license_plate(self):
        if self.new_license_plate:
            self.new_license_plate = self.env['fleet.vehicle.log.contract'].format_license_plate_input(
                self.new_license_plate
            )

    def action_confirm(self):
        self.ensure_one()
        contract = self.contract_id
        if contract.state != 'open':
            raise ValidationError(
                _('This document is not running. You can edit the license plate on the form without this wizard.')
            )

        Contract = self.env['fleet.vehicle.log.contract']
        new_plate = Contract.format_license_plate_input(self.new_license_plate)
        if not new_plate:
            raise ValidationError(_('Please enter a new license plate.'))

        old_plate = contract.license_plate
        if (old_plate or '') == (new_plate or ''):
            raise ValidationError(_('The new license plate must differ from the current one.'))

        pattern = r'^[A-Za-z]{1,2}\s*\d{1,4}\s*[A-Za-z]{0,3}$'
        if not re.match(pattern, new_plate):
            raise ValidationError(
                _('Invalid license plate format.\n'
                  'Expected: [1-2 letters] [1-4 digits] [0-3 letters], e.g. B 1234 ABC or B 1234')
            )

        contract.with_context(x_fleet_license_plate_wizard_ok=True).write(
            {'license_plate': new_plate}
        )
        contract._apply_fleet_contract_auto_name()
        contract._sync_vehicle_analytic_account_from_running_contract()
        aa = contract.vehicle_id.analytic_account_id
        contract.message_post(
            body=_(
                'License plate was changed from "%(old)s" to "%(new)s" via the change-plate wizard. '
                'Analytic account on the vehicle is now: %(aa)s'
            )
            % {
                'old': old_plate or '-',
                'new': new_plate or '-',
                'aa': aa.display_name if aa else '-',
            }
        )
        return {'type': 'ir.actions.act_window_close'}