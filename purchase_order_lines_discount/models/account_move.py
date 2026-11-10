from contextlib import contextmanager

from odoo import models


class AccountMove(models.Model):
    _inherit = "account.move"

    def _prepare_product_base_line_for_taxes_computation(self, product_line):
        if product_line.other_cost_deduction:
            product_line._validate_other_cost_input()
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
        if (self.is_purchase_document(include_receipts=True)
                and product_line.display_type == 'product'
                and product_line.other_cost_deduction and product_line.quantity):
            # First extract the original DPP, including for price-included
            # taxes. Deduct once from DPP, not once per unit or from gross.
            self.env['account.tax']._add_tax_details_in_base_line(base_line, self.company_id)
            excluded = base_line.pop('tax_details')['raw_total_excluded_currency']
            base_line.update(
                price_unit=(excluded - product_line.other_cost_deduction) / base_line['quantity'],
                discount=0.0, special_mode='total_excluded',
            )
        return base_line

    @contextmanager
    def _sync_tax_lines(self, container):
        def fixed_discount_values():
            return {
                line: (
                    (line.fixed_discount, line.fixed_discount_type, line.other_cost_deduction),
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

        # Odoo tracks price/quantity/discount, not our amount-only inputs.
        # Increase then restore the original unit price to request native tax
        # synchronization without temporarily reducing DPP below the deduction.
        prices = {line: line.price_unit for line in stale_lines}
        for line, price in prices.items():
            line.price_unit = price + max(abs(price) * 0.01, 1.0)
        with super()._sync_tax_lines({'records': stale_lines.move_id}):
            for line, price in prices.items():
                line.price_unit = price
