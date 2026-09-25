from odoo import models, fields


class FleetContractVendorBillWizard(models.TransientModel):
    _name = 'fleet.contract.vendor.bill.wizard'
    _description = 'Create Vendor Bill from Fleet Documents'

    contract_ids = fields.Many2many(
        'fleet.vehicle.log.contract',
        'fleet_contract_vendor_bill_wizard_rel',
        'wizard_id',
        'contract_id',
        string="Documents",
    )
    partner_id = fields.Many2one('res.partner', string="Vendor", required=True)

    def action_confirm(self):
        self.ensure_one()
        return self.contract_ids._create_vendor_bill(self.partner_id)
