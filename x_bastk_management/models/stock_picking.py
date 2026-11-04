# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError

from .bastk_management import OPEN_BASTK_STATES


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    bastk_id = fields.Many2one(
        'bastk.management',
        string='BASTK Reference',
        copy=False,
        help='BASTK reference for this Delivery Order.',
        tracking=True,
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

    @api.depends(
        'source_bastk_ids', 'source_bastk_ids.vehicle_id', 'fleet_vehicle_ids', 'picking_type_code',
        'move_line_ids.lot_id.fleet_vehicle_id', 'move_line_ids.quantity',
    )
    def _compute_source_bastk_count(self):
        for picking in self:
            picking.source_bastk_count = len(picking.source_bastk_ids)
            picking.bastk_pending_vehicle_ids = (
                picking._bastk_unit_vehicles() - picking.source_bastk_ids.vehicle_id
            )

    def _bastk_unit_vehicles(self):
        """Vehicles getting a BASTK of their own from this transfer: those registered
        by a receipt, or those of a delivery of several units (a BASTK covers one unit).
        A delivery of a single unit keeps its only BASTK linked through bastk_id.
        """
        self.ensure_one()
        if self.picking_type_code != 'outgoing':
            return self.fleet_vehicle_ids
        vehicles = self.move_line_ids.filtered(lambda ml: ml.quantity > 0).lot_id.fleet_vehicle_id
        return vehicles if len(vehicles) > 1 else self.env['fleet.vehicle']

    def action_create_bastk(self):
        self.ensure_one()
        if not self.has_vehicle_product:
            raise UserError(_('BASTK can only be created for a transfer containing a fleet product.'))
        Bastk = self.env['bastk.management']
        if self._bastk_unit_vehicles():
            Bastk._check_no_open_bastk(self.bastk_pending_vehicle_ids)
            return self._action_create_bastk_per_vehicle()
        Bastk._check_no_open_bastk(
            self.bastk_id.vehicle_id
            | self.move_line_ids.lot_id.fleet_vehicle_id
            | self.move_ids.origin_returned_move_id.move_line_ids.lot_id.fleet_vehicle_id
        )
        return self._action_create_single_bastk()

    def _link_open_bastk_from_origin(self, origin):
        """Return of a delivered unit continues the BASTK that took it out (Submit In)
        instead of getting a new BASTK: link it to the BASTK of the original delivery,
        or else to the only open BASTK of the returned unit(s). A return can continue
        one BASTK only, so units with a BASTK each are returned one by one."""
        self.ensure_one()
        if self.bastk_id or self.picking_type_code != 'incoming' or origin.picking_type_code != 'outgoing':
            return
        bastk = origin.bastk_id.filtered(lambda b: b.state in OPEN_BASTK_STATES)
        if not bastk:
            vehicles = self.move_ids.origin_returned_move_id.move_line_ids.lot_id.fleet_vehicle_id
            open_bastks = self.env['bastk.management'].search([
                ('vehicle_id', 'in', vehicles.ids), ('state', 'in', OPEN_BASTK_STATES),
            ]) if vehicles else self.env['bastk.management']
            if len(open_bastks) > 1:
                raise UserError(_(
                    'These units each have their own open BASTK (%s). Return them one unit at a time.',
                    ', '.join(open_bastks.mapped('name')),
                ))
            bastk = open_bastks
        if bastk:
            self.bastk_id = bastk
            self.message_post(body=_('Linked to BASTK %s: continue it with Submit In.', bastk._get_html_link()))

    def _action_create_bastk_per_vehicle(self):
        """GR with registered vehicles or DO of several units: one BASTK per vehicle,
        only the BASTK Type is asked."""
        if not self.bastk_pending_vehicle_ids:
            raise UserError(_('Every vehicle of this transfer already has a BASTK.'))
        return {
            'name': _('Create BASTK'),
            'type': 'ir.actions.act_window',
            'res_model': 'bastk.create.from.picking.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_picking_id': self.id},
        }

    def _create_bastk_per_vehicle(self, bastk_type):
        """Create the missing BASTK of this transfer (one per vehicle) and return them."""
        self.ensure_one()
        vehicles = self.bastk_pending_vehicle_ids
        if not vehicles:
            raise UserError(_('Every vehicle of this transfer already has a BASTK.'))
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
                vehicle = line.lot_id.fleet_vehicle_id
                if vehicle and vehicle.analytic_account_id == line.analytic_account_id:
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

    def _fleet_source_lot(self):
        if self.bastk_id and self.bastk_id.vehicle_id.lot_id and self.picking_type_code != 'incoming':
            return self.bastk_id.vehicle_id.lot_id
        return super()._fleet_source_lot()

    def _fleet_source_label(self):
        if self.bastk_id and self.picking_type_code != 'incoming':
            return _('BASTK %s', self.bastk_id.name)
        return super()._fleet_source_label()

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
        for picking in self:
            if picking.is_asset_registered:
                continue
            if picking.picking_type_code != 'incoming' or picking.state != 'done':
                continue
            if picking.bastk_id and picking.bastk_id.vehicle_id:
                picking.is_asset_registered = bool(picking.bastk_id.vehicle_id.lot_id)


class StockMove(models.Model):
    _inherit = 'stock.move'

    bastk_unit_id = fields.Many2one(
        'bastk.management',
        string='BASTK',
        compute='_compute_bastk_unit',
        compute_sudo=True,
        help='BASTK of the unit delivered on this line.',
    )
    bastk_out_date = fields.Date(
        string='Tanggal BASTK Keluar',
        compute='_compute_bastk_unit',
        compute_sudo=True,
    )

    @api.depends(
        'picking_id.bastk_id.vehicle_id', 'picking_id.bastk_id.start_date',
        'picking_id.source_bastk_ids.vehicle_id', 'picking_id.source_bastk_ids.start_date',
        'picking_id.picking_type_code', 'move_line_ids.lot_id',
    )
    def _compute_bastk_unit(self):
        for move in self:
            bastk = self.env['bastk.management']
            if move.picking_id.picking_type_code == 'outgoing':
                lots = move.move_line_ids.lot_id
                bastk = (move.picking_id.bastk_id | move.picking_id.source_bastk_ids).filtered(
                    lambda b: b.vehicle_id.lot_id in lots
                )[-1:]
            move.bastk_unit_id = bastk
            move.bastk_out_date = bastk.start_date


class StockReturnPicking(models.TransientModel):
    _inherit = 'stock.return.picking'

    def _create_return(self):
        new_picking = super()._create_return()
        if self.picking_id:
            new_picking._link_open_bastk_from_origin(self.picking_id)
        return new_picking
