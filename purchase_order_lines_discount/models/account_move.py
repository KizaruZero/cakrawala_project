from contextlib import contextmanager

from odoo import models


class AccountMove(models.Model):
    _inherit = "account.move"

    def _prepare_product_base_line_for_taxes_computation(self, product_line):
        base_line = super()._prepare_product_base_line_for_taxes_computation(product_line)
        if (
            self.is_purchase_document(include_receipts=True)
            and product_line._uses_fixed_discount_amount()
            and product_line.fixed_discount
            and product_line.quantity
        ):
            base_line['discount'] = 0.0
            base_line['price_unit'] = (
                base_line['price_unit'] * base_line['quantity'] - product_line.fixed_discount
            ) / base_line['quantity']
        return base_line

    @contextmanager
    def _sync_tax_lines(self, container):
        def fixed_discount_values():
            return {
                line: (
                    (line.fixed_discount, line.fixed_discount_type),
                    (line.price_unit, line.quantity, line.discount),
                )
                for move in container['records']
                if move.state == 'draft' and move.is_purchase_document(include_receipts=True)
                for line in move.line_ids
                if line.display_type == 'product'
            }

        values_before = fixed_discount_values()
        with super()._sync_tax_lines(container):
            yield

        stale_lines = self.env['account.move.line']
        for line, (fixed_values, tracked_values) in fixed_discount_values().items():
            fixed_values_before, tracked_values_before = values_before.get(line, (fixed_values, tracked_values))
            if fixed_values != fixed_values_before and tracked_values == tracked_values_before:
                stale_lines |= line
        if not stale_lines:
            return

        discounts = {line: line.discount for line in stale_lines}
        for line, discount in discounts.items():
            line.discount = 0.0 if discount else 100.0
        with super()._sync_tax_lines({'records': stale_lines.move_id}):
            for line, discount in discounts.items():
                line.discount = discount
