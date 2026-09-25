from odoo import api, fields, models


class BastkCreateFromPickingWizard(models.TransientModel):
    _name = 'bastk.create.from.picking.wizard'
    _description = 'Create BASTK from Goods Receipt'

    picking_id = fields.Many2one('stock.picking', required=True, readonly=True)
    bastk_type_id = fields.Many2one('bastk.type', string='BASTK Type', required=True)
    vehicle_ids = fields.Many2many(
        'fleet.vehicle',
        'bastk_create_from_picking_wizard_vehicle_rel',
        'wizard_id',
        'vehicle_id',
        string='Vehicles',
        compute='_compute_vehicle_ids',
    )

    @api.depends('picking_id')
    def _compute_vehicle_ids(self):
        for wizard in self:
            wizard.vehicle_ids = wizard.picking_id.bastk_pending_vehicle_ids

    def action_confirm(self):
        self.ensure_one()
        self.picking_id._create_bastk_per_vehicle(self.bastk_type_id)
        return self.picking_id.action_view_source_bastk()
