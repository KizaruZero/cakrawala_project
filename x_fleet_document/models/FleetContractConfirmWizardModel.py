from odoo import models, fields


class FleetContractConfirmWizard(models.TransientModel):
    _name = 'fleet.contract.confirm.wizard'
    _description = 'Confirm Running Contract'

    contract_id = fields.Many2one('fleet.vehicle.log.contract')

    def action_confirm(self):
        self.ensure_one()
        contract = self.contract_id

        contract._apply_fleet_contract_auto_name()
        contract.write({'state': 'open'})
        contract._sync_vehicle_analytic_account_from_running_contract()
