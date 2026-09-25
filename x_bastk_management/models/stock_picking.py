# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    bastk_id = fields.Many2one(
        'bastk.management',
        string='BASTK Reference',
        copy=False,
        help='BASTK reference for this Delivery Order.',
    )
    bastk_sale_order_id = fields.Many2one(
        'sale.order',
        string='BASTK Sales Order',
        compute='_compute_bastk_sale_order_id',
        readonly=True,
    )

    bastk_date = fields.Date(string='BASTK Date', related='bastk_id.start_date', readonly=True)

    source_bastk_ids = fields.One2many(
        'bastk.management',
        'source_picking_id',
        string='Generated BASTK',
        help='BASTK created from this Goods Receipt, one per received vehicle.',
    )
    source_bastk_count = fields.Integer(compute='_compute_source_bastk_count', string='BASTK Count')
    bastk_pending_vehicle_ids = fields.Many2many(
        'fleet.vehicle',
        compute='_compute_source_bastk_count',
        string='Vehicles without BASTK',
    )

    @api.depends('source_bastk_ids', 'source_bastk_ids.vehicle_id', 'fleet_vehicle_ids')
    def _compute_source_bastk_count(self):
        for picking in self:
            picking.source_bastk_count = len(picking.source_bastk_ids)
            picking.bastk_pending_vehicle_ids = (
                picking.fleet_vehicle_ids - picking.source_bastk_ids.vehicle_id
            )

    def action_create_bastk(self):
        self.ensure_one()
        if self.fleet_vehicle_ids:
            return self._action_create_bastk_per_vehicle()
        return self._action_create_single_bastk()

    def _action_create_bastk_per_vehicle(self):
        """GR with registered vehicles: one BASTK per vehicle, only the BASTK Type is asked."""
        if not self.bastk_pending_vehicle_ids:
            raise UserError(_('Every vehicle of this receipt already has a BASTK.'))
        return {
            'name': _('Create BASTK'),
            'type': 'ir.actions.act_window',
            'res_model': 'bastk.create.from.picking.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_picking_id': self.id},
        }

    def _create_bastk_per_vehicle(self, bastk_type):
        """Create the missing BASTK of this receipt (one per vehicle) and return them."""
        self.ensure_one()
        vehicles = self.bastk_pending_vehicle_ids
        if not vehicles:
            raise UserError(_('Every vehicle of this receipt already has a BASTK.'))
        bastks = self.env['bastk.management'].create([{
            'bastk_type_id': bastk_type.id,
            'partner_id': self.partner_id.id,
            'vehicle_id': vehicle.id,
            'sale_order_id': self.sale_id.id,
            'source_picking_id': self.id,
        } for vehicle in vehicles])
        self.message_post(body=_('BASTK created: %s') % ', '.join(bastks.mapped('name')))
        return bastks

    def action_view_source_bastk(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('x_bastk_management.action_bastk')
        bastks = self.source_bastk_ids
        if len(bastks) == 1:
            action['views'] = [(self.env.ref('x_bastk_management.view_bastk_form').id, 'form')]
            action['res_id'] = bastks.id
        else:
            action['domain'] = [('id', 'in', bastks.ids)]
            action['context'] = {'create': False}
        return action

    def _action_create_single_bastk(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('x_bastk_management.action_bastk')
        
        from odoo import Command
        
        vehicle_id = False
        for line in self.move_line_ids:
            if line.lot_id and line.analytic_account_id:
                vehicle = self.env['fleet.vehicle'].search([
                    ('asset_number', '=', line.lot_id.name),
                    ('analytic_account_id', '=', line.analytic_account_id.id)
                ], limit=1)
                if vehicle:
                    vehicle_id = vehicle.id
                    break

        action['context'] = {
            'default_partner_id': self.partner_id.id,
            'default_picking_ids': [Command.link(self.id)],
            'default_sale_order_id': self.sale_id.id,
        }
        if vehicle_id:
            action['context']['default_vehicle_id'] = vehicle_id
            
        action['views'] = [(self.env.ref('x_bastk_management.view_bastk_form').id, 'form')]
        return action

    def action_open_bastk(self):
        self.ensure_one()
        return {
            'name': 'BASTK',
            'type': 'ir.actions.act_window',
            'view_mode': 'form',
            'res_model': 'bastk.management',
            'res_id': self.bastk_id.id,
        }


    @api.depends('bastk_id', 'bastk_id.sale_order_id', 'sale_id')
    def _compute_bastk_sale_order_id(self):
        for picking in self:
            if picking.bastk_id and picking.bastk_id.sale_order_id:
                picking.bastk_sale_order_id = picking.bastk_id.sale_order_id
            else:
                picking.bastk_sale_order_id = picking.sale_id

    def _update_bastk_so_reference(self):
        for picking in self.filtered(
            lambda p: p.state == 'done'
            and p.picking_type_code == 'outgoing'
            and p.bastk_id
            and p.sale_id
        ):
            if picking.bastk_id.sale_order_id != picking.sale_id:
                picking.bastk_id.write({'sale_order_id': picking.sale_id.id})

    def _requires_bastk_reference(self):
        self.ensure_one()
        return False

    def _check_bastk_reference_required(self):
        pass

    def button_validate(self):
        return super().button_validate()

    def _action_done(self):
        res = super()._action_done()
        self._update_bastk_so_reference()
        return res

    @api.depends(
        'bastk_id',
        'bastk_id.vehicle_id',
        'bastk_id.vehicle_id.asset_number',
    )
    def _compute_is_asset_registered(self):
        """Extend base compute: jika lot_id tidak ada di move_line (kasus GR dari BASTK),
        fallback ke cek vehicle di BASTK sudah terdaftar di fleet."""
        super()._compute_is_asset_registered()
        FleetVehicle = self.env['fleet.vehicle']
        for picking in self:
            # Hanya proses yang belum dianggap registered oleh base compute
            if picking.is_asset_registered:
                continue
            if picking.picking_type_code != 'incoming' or picking.state != 'done':
                continue
            # Jika tidak ada lot_id di move_line tapi ada BASTK vehicle, cek fleet
            if picking.bastk_id and picking.bastk_id.vehicle_id:
                asset_number = picking.bastk_id.vehicle_id.asset_number
                if asset_number:
                    picking.is_asset_registered = FleetVehicle.search_count(
                        [('asset_number', '=', asset_number)]
                    ) > 0
