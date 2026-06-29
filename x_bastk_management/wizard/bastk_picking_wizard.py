# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import UserError

class BastkPickingWizard(models.TransientModel):
    _name = 'bastk.picking.wizard'
    _description = 'BASTK Picking Wizard'

    bastk_id = fields.Many2one('bastk.management', string='BASTK', required=True)
    picking_type_code = fields.Selection([
        ('incoming', 'Receipt'),
        ('outgoing', 'Delivery'),
    ], string='Operation Type Code', required=True)
    picking_type_id = fields.Many2one(
        'stock.picking.type',
        string='Operation Type',
        required=True
    )

    @api.onchange('picking_type_code')
    def _onchange_picking_type_code(self):
        if self.picking_type_code:
            return {'domain': {'picking_type_id': [('code', '=', self.picking_type_code)]}}
        return {'domain': {'picking_type_id': []}}

    def action_create_picking(self):
        self.ensure_one()
        if not self.picking_type_id:
            raise UserError('Please select an Operation Type.')

        picking_vals = {
            'picking_type_id': self.picking_type_id.id,
            'location_id': self.picking_type_id.default_location_src_id.id,
            'location_dest_id': self.picking_type_id.default_location_dest_id.id,
            'origin': self.bastk_id.name,
            'bastk_id': self.bastk_id.id,
        }
        
        if self.bastk_id.partner_id:
            picking_vals['partner_id'] = self.bastk_id.partner_id.id

        vehicle = self.bastk_id.vehicle_id
        product = vehicle.product_id

        if product:
            move_vals = {
                'product_id': product.id,
                'description_picking': product.name,
                'product_uom': product.uom_id.id,
                'product_uom_qty': 1.0,
                'location_id': self.picking_type_id.default_location_src_id.id,
                'location_dest_id': self.picking_type_id.default_location_dest_id.id,
            }

            # Replacement Car logic
            if vehicle.fleet_sub_status_id and vehicle.fleet_sub_status_id.name == 'Replacement Car':
                if 'replacement_car' in self.env['stock.move']._fields:
                    move_vals['replacement_car'] = True
                if 'is_replace' in self.env['stock.move']._fields:
                    move_vals['is_replace'] = True

            # Analytic Distribution
            if vehicle.analytic_account_id:
                move_vals['x_spk_analytic_distribution'] = {str(vehicle.analytic_account_id.id): 100}

            # Serial Number & Vehicle Data on move_line
            lot = self.env['stock.lot'].search([('name', '=', vehicle.asset_number)], limit=1)
            
            vehicle_year_id = False
            if vehicle.model_year:
                year_record = self.env['vehicle.year'].search([('name', '=', vehicle.model_year)], limit=1)
                if year_record:
                    vehicle_year_id = year_record.id
                    
            vehicle_color_id = False
            if vehicle.color:
                color_record = self.env['vehicle.color'].search([('name', '=', vehicle.color)], limit=1)
                if color_record:
                    vehicle_color_id = color_record.id

            move_line_vals = {
                'product_id': product.id,
                'product_uom_id': product.uom_id.id,
                'quantity': 1.0,
                'location_id': self.picking_type_id.default_location_src_id.id,
                'location_dest_id': self.picking_type_id.default_location_dest_id.id,
                'initial_license_plate': getattr(vehicle, 'initial_license_plate', False) or getattr(vehicle, 'license_plate', False),
                'chassis_number': getattr(vehicle, 'chassis_number', False),
                'engine_number': getattr(vehicle, 'engine_number', False),
                'vehicle_year_id': vehicle_year_id,
                'vehicle_color_id': vehicle_color_id,
            }

            if lot:
                move_line_vals['lot_id'] = lot.id
                move_line_vals['lot_name'] = lot.name

            move_vals['move_line_ids'] = [(0, 0, move_line_vals)]
            picking_vals['move_ids'] = [(0, 0, move_vals)]

        picking = self.env['stock.picking'].create(picking_vals)

        return {
            'name': 'Transfers',
            'type': 'ir.actions.act_window',
            'res_model': 'stock.picking',
            'view_mode': 'form',
            'res_id': picking.id,
            'target': 'current',
        }
