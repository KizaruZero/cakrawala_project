# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

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

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        bastk_id = res.get('bastk_id') or self.env.context.get('default_bastk_id')
        code = res.get('picking_type_code') or self.env.context.get('default_picking_type_code')
        if bastk_id and code:
            bastk = self.env['bastk.management'].browse(bastk_id)
            wh = bastk._get_vehicle_warehouse()
            if wh:
                if code == 'outgoing':
                    picking_type = (wh.out_type_id if wh else False) or self.env['stock.picking.type'].search([
                        ('code', '=', 'outgoing'),
                        ('warehouse_id', '=', wh.id),
                    ], limit=1)
                elif code == 'incoming':
                    picking_type = (wh.in_type_id if wh else False) or self.env['stock.picking.type'].search([
                        ('code', '=', 'incoming'),
                        ('warehouse_id', '=', wh.id),
                    ], limit=1)
                else:
                    picking_type = False
                if picking_type:
                    res['picking_type_id'] = picking_type.id
        return res

    @api.onchange('picking_type_code', 'bastk_id')
    def _onchange_picking_type_code(self):
        if not self.picking_type_code:
            return {'domain': {'picking_type_id': []}}

        domain = [('code', '=', self.picking_type_code)]
        bastk = self.bastk_id or (self.env.context.get('default_bastk_id') and self.env['bastk.management'].browse(self.env.context['default_bastk_id']))
        if bastk:
            wh = bastk._get_vehicle_warehouse()
            if wh:
                domain.append(('warehouse_id', '=', wh.id))
                if self.picking_type_code == 'outgoing' and wh.out_type_id:
                    self.picking_type_id = wh.out_type_id
                elif self.picking_type_code == 'incoming' and wh.in_type_id:
                    self.picking_type_id = wh.in_type_id
                else:
                    self.picking_type_id = self.env['stock.picking.type'].search(domain, limit=1)
            else:
                self.picking_type_id = self.env['stock.picking.type'].search(domain, limit=1)
        else:
            self.picking_type_id = self.env['stock.picking.type'].search(domain, limit=1)
        return {'domain': {'picking_type_id': domain}}

    def action_create_picking(self):
        self.ensure_one()
        if not self.picking_type_id:
            raise UserError('Please select an Operation Type.')

        if self.picking_type_code == 'outgoing':
            self.bastk_id._check_vehicle_stock_availability()

        src_location = self.picking_type_id.default_location_src_id
        dest_location = self.picking_type_id.default_location_dest_id

        if self.picking_type_code == 'outgoing':
            internal_quants = self.bastk_id._get_vehicle_internal_quants()
            if internal_quants:
                src_location = internal_quants[0].location_id

        # Goods Receive BASTK adalah pengembalian unit, bukan pembelian baru dari
        # vendor. Sumbernya harus lokasi tujuan Goods Issue-nya (mis. Customers)
        # supaya quant lama di sana ikut terhapus. Kalau memakai default Operation
        # Type (Vendors -> WH/Stock), unit jadi tercatat di dua tempat dan Goods
        # Issue berikutnya diblokir pengecekan serial Odoo.
        if self.picking_type_code == 'incoming':
            if not self.bastk_id.need_submit_out and self.bastk_id.bastk_type_id.need_gr:
                raise ValidationError(_(
                    "BASTK yang tidak memerlukan Submit Out tidak dapat memproses Goods Receive (GR). "
                    "Kasus ini tidak diperbolehkan."
                ))
            issue = self.bastk_id.picking_ids.filtered(
                lambda p: p.picking_type_code == 'outgoing' and p.state == 'done'
            ).sorted('date_done')[-1:]
            if issue:
                src_location = issue.location_dest_id

        picking_vals = {
            'picking_type_id': self.picking_type_id.id,
            'location_id': src_location.id,
            'location_dest_id': dest_location.id,
            'origin': self.bastk_id.name,
            'bastk_id': self.bastk_id.id,
        }
        
        if self.bastk_id.partner_id:
            picking_vals['partner_id'] = self.bastk_id.partner_id.id

        vehicle = self.bastk_id.vehicle_id

        lot = False
        product = False
        if vehicle.asset_number:
            lot = self.env['stock.lot'].search([
                ('name', '=', vehicle.asset_number),
                ('company_id', '=', self.env.company.id),
            ], limit=1)
            if lot:
                product = lot.product_id

        if not product:
            product = vehicle.product_id

        if product:
            move_vals = {
                'product_id': product.id,
                'description_picking': product.name,
                'product_uom': product.uom_id.id,
                'product_uom_qty': 1.0,
                'location_id': src_location.id,
                'location_dest_id': dest_location.id,
            }

            if vehicle.fleet_sub_status_id and vehicle.fleet_sub_status_id.name == 'Replacement Car':
                if 'replacement_car' in self.env['stock.move']._fields:
                    move_vals['replacement_car'] = True
                if 'is_replace' in self.env['stock.move']._fields:
                    move_vals['is_replace'] = True

            if vehicle.analytic_account_id:
                move_vals['x_spk_analytic_distribution'] = {str(vehicle.analytic_account_id.id): 100}

            vehicle_year_id = False
            if vehicle.model_year:
                year_record = self.env['vehicle.year'].search([('name', '=', vehicle.model_year)], limit=1)
                if year_record:
                    vehicle_year_id = year_record.id
            if not vehicle_year_id and lot and hasattr(lot, 'vehicle_year_id') and lot.vehicle_year_id:
                vehicle_year_id = lot.vehicle_year_id.id
            if not vehicle_year_id:
                year_fallback = self.env['vehicle.year'].search([], limit=1)
                if year_fallback:
                    vehicle_year_id = year_fallback.id

            vehicle_color_id = False
            if vehicle.color:
                color_record = self.env['vehicle.color'].search([('name', '=', vehicle.color)], limit=1)
                if color_record:
                    vehicle_color_id = color_record.id
            if not vehicle_color_id and lot and hasattr(lot, 'vehicle_color_id') and lot.vehicle_color_id:
                vehicle_color_id = lot.vehicle_color_id.id
            if not vehicle_color_id:
                color_fallback = self.env['vehicle.color'].search([], limit=1)
                if color_fallback:
                    vehicle_color_id = color_fallback.id

            vehicle_model_id = vehicle.model_id.id if vehicle.model_id else (lot.vehicle_model_id.id if lot and hasattr(lot, 'vehicle_model_id') and lot.vehicle_model_id else False)

            move_line_vals = {
                'product_id': product.id,
                'product_uom_id': product.uom_id.id,
                'quantity': 1.0,
                'location_id': src_location.id,
                'location_dest_id': dest_location.id,
                'initial_license_plate': getattr(vehicle, 'initial_license_plate', False) or getattr(vehicle, 'license_plate', False),
                'chassis_number': getattr(vehicle, 'chassis_number', False),
                'engine_number': getattr(vehicle, 'engine_number', False),
                'vehicle_year_id': vehicle_year_id,
                'vehicle_color_id': vehicle_color_id,
                'vehicle_model_id': vehicle_model_id,
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
