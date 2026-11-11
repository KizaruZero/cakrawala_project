from odoo import api, fields, models


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    is_pdu_rc = fields.Boolean(string='PDU/RC', default=False)

    def _previous_rental_product_line(self):
        """Previous real product row, in the order shown by the one2many.

        Also works with unsaved sibling rows in the Add a line editor. Existing
        order prices are never recomputed just because another unit is added.
        """
        self.ensure_one()
        previous = self.browse()
        for candidate in self.order_id.order_line.sorted('sequence'):
            if candidate == self:
                break
            if candidate.sequence > self.sequence:
                break
            if candidate.product_id and not candidate.display_type and not candidate.is_downpayment:
                previous = candidate
        return previous

    def _reset_price_unit(self):
        # Both computed prices and the native product onchange use this hook.
        # Retain the native technical price, so an inherited quote is treated
        # as a manual price rather than silently repriced on quantity changes.
        result = super()._reset_price_unit()
        self.ensure_one()
        if (not self._origin and self.product_id and not self.display_type
                and not self.is_downpayment and self.order_id.is_rental_order
                and self.order_id.state == 'sale'):
            previous = self._previous_rental_product_line()
            if previous:
                self.price_unit = previous.price_unit
        return result

    @api.model_create_multi
    def create(self, vals_list):
        values_list = [dict(values) for values in vals_list]
        sources = {}
        default_order_id = self.env.context.get('default_order_id')
        for values in values_list:
            order_id = values.get('order_id', default_order_id)
            if not order_id or values.get('display_type') or values.get('is_downpayment'):
                continue
            order = self.env['sale.order'].browse(order_id)
            if not order.is_rental_order or order.state != 'sale' or not values.get('product_id'):
                continue
            if order_id not in sources:
                sources[order_id] = [
                    (line.sequence, line.price_unit)
                    for line in order.order_line.sorted('sequence')
                    if line.product_id and not line.display_type and not line.is_downpayment
                ]
            sequence = values.get('sequence', self.default_get(['sequence']).get('sequence', 10))
            candidates = [source for source in sources[order_id] if source[0] <= sequence]
            if 'price_unit' not in values and candidates:
                # Latest row wins on tied sequences (the usual Add a line case).
                previous = max(enumerate(candidates), key=lambda item: (item[1][0], item[0]))[1]
                preview = self.new(values)
                super(SaleOrderLine, preview)._reset_price_unit()
                values['price_unit'] = previous[1]
                values['technical_price_unit'] = preview.technical_price_unit
            if 'price_unit' in values:
                price = values['price_unit']
            else:
                # A first unit has no predecessor: retain normal Odoo pricing.
                price = self.new(values).price_unit
            sources[order_id].append((sequence, price))
        # Explicit prices from Input Order generation/imports remain unchanged.
        return super().create(values_list)
