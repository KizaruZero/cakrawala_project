"""Read-only invoice detail tables. Accounting lines remain the source of truth."""
import re

from odoo import models


_PRINT_PERIOD = re.compile(
    r'^(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec) '
    r'\d{1,2}, \d{4} - (?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec) '
    r'\d{1,2}, \d{4}$'
)


class AccountMove(models.Model):
    _inherit = 'account.move'

    def _rental_invoice_print_unit_quantity(self, rental_lines):
        """Count contracted vehicles, not billed months or stamp quantities."""
        self.ensure_one()
        orders = self.invoice_line_ids.sale_line_ids.order_id.filtered('is_rental_order')
        if not orders:
            return sum(abs(line.quantity) for line in rental_lines)
        quantity = 0.0
        for order in orders:
            inputs = order.input_line_ids.filtered(lambda line: line.product_id.rent_ok)
            if inputs:
                quantity += sum(abs(line.quantity) for line in inputs)
            else:
                units = order.order_line.filtered(lambda line: (
                    not line.display_type and not line.is_downpayment
                    and (line.product_id.rent_ok or line.is_rental)
                ))
                quantity += sum(abs(line.product_uom_qty) for line in units)
        return quantity

    def _rental_invoice_print_details(self):
        """Return exact ungrouped invoice rows, with rounded native PPN/PPh.

        No browsing uninvoiced order/engine periods and no recomputation/write
        of invoice taxes. Native tax helpers respect price-included/group taxes,
        global rounding and posted/manual tax line amounts in invoice currency.
        """
        self.ensure_one()
        orders = self.invoice_line_ids.sale_line_ids.order_id.filtered('is_rental_order')
        if (self.move_type not in ('out_invoice', 'out_refund') or self.is_et_penalty_invoice
                or not (self.x_is_rental_invoice or orders)):
            return False
        fees = self._customer_invoice_print_fees()
        products = self.invoice_line_ids.filtered(lambda line: line.display_type == 'product')
        rental_lines = products - fees
        unit_quantity = self._rental_invoice_print_unit_quantity(rental_lines)
        base_lines, _tax_lines = self._get_rounded_base_and_tax_lines()
        base_by_line = {base['record'].id: base for base in base_lines}

        def amounts(base, subtotal):
            ppn = pph = other = 0.0
            for tax_data in base.get('tax_details', {}).get('taxes_data', []):
                tax = tax_data['tax']
                label = '%s %s' % (tax.name, tax.tax_group_id.name)
                amount = tax_data['tax_amount_currency']
                if re.search(r'\b(?:pph|wht|withholding)', label, re.IGNORECASE):
                    pph -= amount  # Positive display = deduction; retain its accounting sign.
                elif re.search(r'\b(?:ppn|vat)', label, re.IGNORECASE):
                    ppn += amount
                else:
                    other += amount
            ppn, pph, other = (self.currency_id.round(value) for value in (ppn, pph, other))
            return {'subtotal': subtotal, 'ppn': ppn, 'pph': pph, 'other_tax': other,
                    'total': self.currency_id.round(subtotal + ppn - pph + other)}

        rows = []
        number = 0
        # Deliberately not grouped: preserve the invoice's row order and amounts.
        for line in self.invoice_line_ids.sorted(lambda item: (item.sequence, item.id)):
            if line.display_type != 'product':
                if line.display_type in ('line_section', 'line_subsection', 'line_note'):
                    rows.append({'display_type': line.display_type, 'description': line.name or ''})
                continue
            is_fee = line in fees
            description, plates = line._customer_invoice_print_unit_details()
            paragraphs = description.splitlines()
            periods = [text for text in paragraphs if _PRINT_PERIOD.fullmatch(text.strip())]
            period = '\n'.join(periods)
            if not period and not is_fee and self.x_rental_period_start and self.x_rental_period_end:
                period = '%s - %s' % (self._customer_invoice_print_date(self.x_rental_period_start),
                                     self._customer_invoice_print_date(self.x_rental_period_end))
            notes = '\n'.join(text for text in paragraphs[1:] if text not in periods)
            if not is_fee:
                number += 1
            rows.append({
                'display_type': 'product', 'line_id': line.id,
                'number': number if not is_fee else '', 'is_fee': is_fee,
                'description': paragraphs[0] if paragraphs else (line.product_id.display_name or ''),
                'notes': notes, 'plates': plates if not is_fee else [], 'period': period,
                'billing_month': line.x_billing_month or '',
                'quantity': line.quantity, 'price_unit': line.price_unit,
                **amounts(base_by_line.get(line.id, {}), line.price_subtotal),
            })
        # Native rounding/early-payment adjustment base lines are not Invoice
        # Lines, but must be disclosed when they affect the document total.
        for base in base_lines:
            record = base['record']
            if record.id in products.ids:
                continue
            subtotal = base['tax_details']['total_excluded_currency']
            values = amounts(base, subtotal)
            if any(not self.currency_id.is_zero(values[key]) for key in values):
                rows.append({
                    'display_type': 'product', 'line_id': False, 'number': '', 'is_fee': True,
                    'description': record.name or 'Penyesuaian invoice', 'notes': '', 'plates': [],
                    'period': '', 'billing_month': '', 'quantity': 1, 'price_unit': subtotal, **values,
                })

        detail_rows = [row for row in rows if row['display_type'] == 'product']
        totals = {key: self.currency_id.round(sum(row[key] for row in detail_rows))
                  for key in ('subtotal', 'ppn', 'pph', 'other_tax', 'total')}
        adjustment = self.currency_id.round(self.amount_total - totals['total'])
        if not self.currency_id.is_zero(adjustment):
            rows.append({
                'display_type': 'product', 'line_id': False, 'number': '', 'is_fee': True,
                'description': 'Penyesuaian sesuai total invoice', 'notes': '', 'plates': [],
                'period': '', 'billing_month': '', 'quantity': 1, 'price_unit': adjustment,
                'subtotal': adjustment, 'ppn': 0, 'pph': 0, 'other_tax': 0, 'total': adjustment,
            })
            totals['subtotal'] = self.currency_id.round(totals['subtotal'] + adjustment)
        totals['total'] = self.amount_total
        return {
            'rows': rows, 'totals': totals, 'unit_quantity': unit_quantity,
            'single_unit': unit_quantity <= 1,
            'show_other_tax': any(not self.currency_id.is_zero(row.get('other_tax', 0)) for row in rows),
        }
