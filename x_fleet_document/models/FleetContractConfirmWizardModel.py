from odoo import models, fields


class FleetContractConfirmWizard(models.TransientModel):
    _name = 'fleet.contract.confirm.wizard'
    _description = 'Confirm Running Contract'

    contract_id = fields.Many2one('fleet.vehicle.log.contract')

    def action_confirm(self):
        self.ensure_one()
        self.contract_id.write({'state': 'open'})
