from odoo import _, api, fields, models
from odoo.exceptions import UserError


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    replacement_car_ids = fields.One2many(
        'replacement.car', 'rental_order_id',
        string="Replacement Cars",
        readonly=True,
        groups='fleet.fleet_group_user',
    )
    replacement_car_count = fields.Integer(
        string="Replacement Car Count",
        compute='_compute_replacement_car_count',
    )
    can_create_replacement_car = fields.Boolean(
        string="Can Create RC",
        compute='_compute_can_create_replacement_car',
    )

    def _compute_replacement_car_count(self):
        # sudo: the Rental Order is also opened by users without Fleet access.
        for order in self:
            order.replacement_car_count = len(order.sudo().replacement_car_ids)

    @api.depends('state', 'is_rental_order', 'order_line.is_pdu_rc',
                 'replacement_car_ids.state', 'replacement_car_ids.rental_order_line_id')
    def _compute_can_create_replacement_car(self):
        for order in self:
            order.can_create_replacement_car = bool(order._get_pdu_rc_lines_without_replacement_car())

    def _get_pdu_rc_lines_without_replacement_car(self):
        """PDU/RC lines of a confirmed Rental Order that have no RC yet (a rejected RC does not count)."""
        self.ensure_one()
        if not (self.is_rental_order and self.state == 'sale'):
            return self.env['sale.order.line']
        covered = self.sudo().replacement_car_ids.filtered(
            lambda rc: rc.state != 'rejected'
        ).rental_order_line_id
        return self.order_line.filtered(
            lambda line: line.is_pdu_rc and not line.display_type and line._origin.id not in covered.ids
        )

    def action_create_replacement_car(self):
        """One RC for every ticked PDU/RC line that has no RC yet."""
        self.ensure_one()
        lines = self._get_pdu_rc_lines_without_replacement_car()
        if not lines:
            raise UserError(_("Tidak ada baris PDU/RC yang belum dibuatkan RC di Rental Order ini."))
        cars = self.env['replacement.car'].create([line._prepare_replacement_car_vals() for line in lines])
        self.message_post(body=_("Replacement Car dibuat: %s", ", ".join(cars.mapped('display_name'))))
        return self._action_open_replacement_cars(cars)

    def action_view_replacement_car(self):
        self.ensure_one()
        return self._action_open_replacement_cars(self.replacement_car_ids)

    def _action_open_replacement_cars(self, cars):
        action = {
            'type': 'ir.actions.act_window',
            'name': _("Replacement Car"),
            'res_model': 'replacement.car',
            'target': 'current',
        }
        if len(cars) == 1:
            action.update(view_mode='form', res_id=cars.id)
        else:
            action.update(view_mode='list,form', domain=[('id', 'in', cars.ids)])
        return action


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    def _get_pdu_rc_vehicle(self):
        """The unit of this line: its Fleet Vehicle, else the unit of the lot on its delivery.

        A delivered lot wins over a reserved one. Empty while no unit is known yet.
        """
        self.ensure_one()
        if self.fleet_vehicle_id:
            return self.fleet_vehicle_id
        # sudo: whoever creates the RC does not necessarily have Inventory access.
        move_lines = self.sudo().move_ids.filtered(
            lambda m: m.state != 'cancel' and m.location_dest_id.usage == 'customer'
        ).move_line_ids.filtered('lot_id')
        move_line = move_lines.sorted(lambda ml: (ml.state != 'done', ml.id))[:1]
        return self.env['fleet.vehicle'].browse(move_line.lot_id.fleet_vehicle_id.id)

    def _prepare_replacement_car_vals(self):
        self.ensure_one()
        order = self.order_id
        start = order.actual_rental_start_date or order.rental_start_date
        today = fields.Date.context_today(self)
        return {
            'rental_order_line_id': self.id,
            'customer_id': order.partner_id.commercial_partner_id.id,
            'vehicle_new_id': self._get_pdu_rc_vehicle().id,
            'request_date': today,
            'pic_name': order.attention_up or order.partner_id.name,
            'estimation_use_date': fields.Date.context_today(self, start) if start else today,
        }
