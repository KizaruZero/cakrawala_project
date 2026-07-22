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

        today = fields.Date.today()
        vehicle = contract.vehicle_id
        History = self.env['fleet.vehicle.license.plate.history']

        # Plat diganti sebelum dokumen expired -> segmen plat lama berakhir hari ini.
        # Cari segmen aktif lewat contract_id (fallback ke valid_until kosong untuk data lama).
        last_history = History.search([
            ('contract_id', '=', contract.id),
            ('license_plate', '=', old_plate),
        ], limit=1, order='id desc')
        if not last_history:
            last_history = History.search([
                ('vehicle_id', '=', vehicle.id),
                ('license_plate', '=', old_plate),
                ('valid_until', '=', False),
            ], limit=1, order='id desc')
        if last_history:
            last_history.valid_until = today

        contract_ctx = contract.with_context(
            x_fleet_license_plate_wizard_ok=True,
            x_skip_plate_history=True,
            skip_history_sync=True,
        )
        contract_ctx.write({'license_plate': new_plate})
        contract_ctx._apply_fleet_contract_auto_name()
        contract_ctx._sync_vehicle_analytic_account_from_running_contract()
        History.create({
            'vehicle_id': vehicle.id,
            'license_plate': new_plate,
            # Dokumen yang sama berlanjut dengan plat baru: berlaku sejak hari penggantian
            # sampai Document Expiration Date dokumen tersebut.
            'valid_from': today,
            'valid_until': contract.expiration_date,
            'contract_id': contract.id,
        })


        aa = vehicle.analytic_account_id
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