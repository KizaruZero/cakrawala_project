from odoo import api, fields, models


class BastkManagementRC(models.Model):
    """Extend bastk.management to track the Replacement Car that originated it."""
    _inherit = 'bastk.management'

    replacement_car_id = fields.Many2one(
        'replacement.car',
        string='RC Reference',
        ondelete='set null',
        readonly=True,
        copy=False,
        tracking=True,
    )

    def _link_rental_order_replacement_car(self):
        """Link a BASTK RO to the RC of its Rental Order line (RO + order line).

        The line is the one delivering the unit of this BASTK, as for the Actual Delivery
        of the rental. A BASTK made by a regular RC keeps its RC.
        """
        ReplacementCar = self.env['replacement.car'].sudo()
        for bastk in self.sudo().filtered('vehicle_id'):
            current = bastk.replacement_car_id
            if current and not current.rental_order_line_id:
                continue
            lines = bastk._get_rental_unit_moves().sale_line_id
            if not lines:
                continue
            car = ReplacementCar.search([
                ('rental_order_line_id', 'in', lines.ids), ('state', '!=', 'rejected'),
            ], order='id desc', limit=1)
            if car and current != car:
                bastk.replacement_car_id = car
            if car:
                car._follow_rental_order_bastk(bastk)

    def action_submit_outside(self):
        self._link_rental_order_replacement_car()
        res = super().action_submit_outside()
        for rec in self:
            if rec.replacement_car_id:
                rec.replacement_car_id._sync_state_from_bastk()
        return res

    def action_submit_inside(self):
        res = super().action_submit_inside()
        for rec in self:
            if rec.replacement_car_id:
                rec.replacement_car_id._sync_state_from_bastk()
        return res

    def action_done(self):
        res = super().action_done()
        for rec in self:
            if rec.replacement_car_id:
                rec.replacement_car_id._sync_state_from_bastk()
        return res

    def write(self, vals):
        res = super().write(vals)
        if 'state' in vals or 'replacement_car_id' in vals:
            for rec in self:
                if rec.replacement_car_id:
                    rec.replacement_car_id._sync_state_from_bastk()
        return res

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._link_rental_order_replacement_car()
        for rec in records:
            if rec.replacement_car_id:
                rec.replacement_car_id._sync_state_from_bastk()
        return records