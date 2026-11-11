"""Read-only invoice detail tables. Accounting lines remain the source of truth."""
import re

from odoo import models


_PRINT_PERIOD = re.compile(
    r'^\d{2}-(?:January|February|March|April|May|June|July|August|September|October|November|December)-\d{4}'
    r' - \d{2}-(?:January|February|March|April|May|June|July|August|September|October|November|December)-\d{4}$'
)


class AccountMove(models.Model):
    _inherit = 'account.move'

    def _rental_invoice_print_unit_quantity(self, rental_lines):
        """Count only vehicles represented on this invoice, never the whole RO.

        Repeated billing months of a linked unit are not additional vehicles.
        Limit a linked source's contribution to the invoiced quantity, so a
        partial invoice of a bulk source line also stays a single-unit invoice.
        Source quantities still distinguish billing months (quantity 12 on an
        annual invoice of a one-unit source) from twelve actual vehicles.
        """
        self.ensure_one()
        source_quantities = {}
        linked_plates = set()
        unlinked_plates = set()
        unlinked_period_quantities = {}
        unidentified_quantity = 0.0
        for line in rental_lines:
            quantity = abs(line.quantity)
            if not quantity:
                continue
            description, unit_codes = line._customer_invoice_print_unit_details()
            plates = set(unit_codes)
            sources = line.sale_line_ids.filtered(lambda source: (
                not source.display_type and not source.is_downpayment
            ))
            if sources:
                key = tuple(sorted(sources.ids))
                source_quantity = sum(abs(source.product_uom_qty) for source in sources)
                count = min(quantity, source_quantity) if source_quantity else quantity
                source_quantities[key] = max(source_quantities.get(key, 0), count)
                linked_plates.update(plates)
            elif plates:
                # Legacy/unlinked monthly copies with the same registration
                # represent one vehicle, not one additional vehicle per month.
                unlinked_plates.update(plates)
                key = tuple(sorted(plates))
                period = tuple(text.strip() for text in description.splitlines()
                               if _PRINT_PERIOD.fullmatch(text.strip()))
                period = period or (line.x_billing_month or '',)
                quantities = unlinked_period_quantities.setdefault(key, {})
                quantities[period] = quantities.get(period, 0) + quantity
            elif not line.sale_line_ids:
                unidentified_quantity += quantity
        # An unlinked aggregate may charge more vehicles than it identifies by
        # plate. Retain that invoice quantity, but not additional billing months.
        unlinked_extra = sum(max(max(periods.values()) - len(plates), 0)
                             for plates, periods in unlinked_period_quantities.items())
        quantity = (sum(source_quantities.values()) + unlinked_extra
                    + len(unlinked_plates - linked_plates) + unidentified_quantity)
        return max(quantity, len(linked_plates | unlinked_plates))

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
        # Keep the full accounting reconciliation above, but never print fees
        # as vehicles or inflate unit-table totals with hidden charge rows.
        unit_rows = [row for row in rows if row['display_type'] != 'product' or not row['is_fee']]
        unit_totals = {key: self.currency_id.round(sum(
            row[key] for row in unit_rows if row['display_type'] == 'product'))
            for key in ('subtotal', 'ppn', 'pph', 'other_tax', 'total')}
        return {
            'rows': rows, 'totals': totals, 'unit_quantity': unit_quantity,
            'unit_rows': unit_rows, 'unit_totals': unit_totals,
            'single_unit': unit_quantity <= 1,
            'show_other_tax': any(not self.currency_id.is_zero(row.get('other_tax', 0)) for row in unit_rows),
        }
