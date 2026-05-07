from odoo import models, fields

class FleetVehicle(models.Model):
    _inherit = 'fleet.vehicle'

    fleet_sub_status = fields.Selection([
        ('short_term', 'Short-term Rent'),
        ('long_term', 'Long-term Rent'),
        ('inventaris', 'Inventaris'),
        ('re_marketing', 'Re-Marketing'),
        ('replacement_car', 'Replacement Car'),
        ('disposal', 'Disposal'),
        ('total_loss_claim', 'Total Loss Claim'),
        ('sold', 'Sold'),
        ('claim_closed', 'Claim Closed')
    ], string='Fleet Sub-Status')
    
    asset_type = fields.Char(string='Asset Type')
    asset_number = fields.Char(string='Asset Number')
    unit_classification = fields.Char(string='Unit Classification')
    assignment_date = fields.Date(string='Assignment Date')
    plan_to_disposal = fields.Boolean(string='Plan to Disposal')
    initial_license_plate = fields.Char(string='Initial License Plate')
    chassis_number = fields.Char(string='Chassis Number')
    engine_number = fields.Char(string='Engine Number')
