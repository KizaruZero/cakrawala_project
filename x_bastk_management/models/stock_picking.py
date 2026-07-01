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
        return self.picking_type_code == 'outgoing' and bool(self.sale_id)

    def _check_bastk_reference_required(self):
        missing = self.filtered(lambda p: p._requires_bastk_reference() and not p.bastk_id)
        if missing:
            raise UserError(
                _('BASTK Reference is required before validating Delivery Order(s) linked to a Sales Order:\n- %s')
                % '\n- '.join(missing.mapped('name'))
            )

    def button_validate(self):
        self._check_bastk_reference_required()
        return super().button_validate()

    def _action_done(self):
        self._check_bastk_reference_required()
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
