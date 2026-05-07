from odoo import api, models, fields
from odoo.exceptions import ValidationError
import logging
_logger = logging.getLogger(__name__)

class FleetContractConfirmWizard(models.TransientModel):
    _name = 'fleet.contract.confirm.wizard'
    _description = 'Confirm Running Contract'

    contract_id = fields.Many2one('fleet.vehicle.log.contract')

    def action_confirm(self):
        self.ensure_one()
        contract = self.contract_id
        
        model_name = contract.vehicle_id.model_id.name if contract.vehicle_id and contract.vehicle_id.model_id else ''

        manufacturer_name = (
            contract.vehicle_id.model_id.brand_id.name
            if contract.vehicle_id
            and contract.vehicle_id.model_id
            and contract.vehicle_id.model_id.brand_id
            else ''
        )

        license_plate = contract.license_plate or ''

        contract.name = f"{contract.cost_subtype_id.name} {manufacturer_name}/{model_name}/{license_plate}"
        
        contract.state = 'open'

        plan = self.env['account.analytic.plan'].search([], limit=1)
        if not plan:
            raise ValidationError("Analytic Plan not found.")

        name = f"{contract.vehicle_id.license_plate} - {contract.vehicle_id.asset_number}"
        
        Analytic = self.env['account.analytic.account']
        existing = Analytic.search([
            ('name', '=', name)
        ], limit=1)

        vals = {
            'name': name,
            'asset_number': contract.vehicle_id.asset_number,
            'license_plate': contract.license_plate,
            'partner_id': contract.insurer_id.id,
            'code': contract.ins_ref,
            'plan_id': plan.id,
            'company_id': contract.company_id.id,
            'currency_id': contract.currency_id.id,
        }

        if existing:
            existing.write(vals)
        else:
            Analytic.create(vals)

        # UPDATE PLAT NOMOR DI KENDARAAN (FLEET)
        # Khusus jika tipe kontrak adalah 'STNK' (is_license_plate=True)
        if contract.cost_subtype_id.is_license_plate:
            contract.vehicle_id.write({
                'license_plate': contract.license_plate
            })