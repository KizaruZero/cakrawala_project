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
