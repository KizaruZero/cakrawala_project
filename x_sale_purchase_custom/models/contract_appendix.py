"""Read-only data for the vehicle-rental Word contract appendix."""
import re

from odoo import models


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def _contract_appendix_context(self):
        self.ensure_one()
        months = ('Januari Februari Maret April Mei Juni Juli Agustus September '
                  'Oktober November Desember').split()
        start = self.contract_start_date
        start_label = f'{start.day:02d} {months[start.month - 1]} {start.year}' if start else '-'
        frequency = {
            'monthly': 'Bulanan', 'per_3_months': 'Per 3 bulan',
            'per_6_months': 'Per 6 bulan', 'yearly': 'Tahunan',
            'as_duration': 'Sesuai durasi sewa',
        }.get(self.invoicing_cycle_period, '-')
        lines = self.order_line.filtered(
            lambda line: not line.display_type and not line.is_downpayment and line.product_id
        ).sorted(lambda line: (line.sequence, line.id))
        bases = [line._prepare_base_line_for_taxes_computation() for line in lines]
        tax_model = self.env['account.tax']
        tax_model._add_tax_details_in_base_lines(bases, self.company_id)
        tax_model._round_base_lines_tax_details(bases, self.company_id)

        def amount(value):
            # Contract table follows the reference's Indonesian number notation.
            decimals = self.currency_id.decimal_places
            return f'{value:,.{decimals}f}'.translate(str.maketrans(',.', '.,'))

        rows = []
        for index, (line, base) in enumerate(zip(lines, bases), 1):
            vehicle = line.fleet_vehicle_id
            if vehicle and not vehicle.has_access('read'):
                vehicle = self.env['fleet.vehicle']
            brand = line.product_id.fleet_brand_id or vehicle.model_id.brand_id
            year_values = line.product_id.product_template_attribute_value_ids.filtered(
                lambda value: value.attribute_id.name.lower() in ('tahun', 'year', 'model year')
            )
            year = vehicle.model_year or ', '.join(year_values.mapped('name')) or '-'
            details = base['tax_details']
            ppn = pph = 0.0
            for item in details.get('taxes_data', []):
                tax = item['tax']
                label = f'{tax.name} {tax.tax_group_id.name}'
                value = item['tax_amount_currency']
                if re.search(r'\b(?:pph|wht|withholding)', label, re.I):
                    pph -= value
                elif re.search(r'\b(?:ppn|vat)', label, re.I):
                    ppn += value
            description = line.product_id.with_context(display_default_code=False).display_name
            if line.product_uom_qty != 1:
                description += f' ({line.product_uom_qty:g} unit)'
            rows.append({
                'number': index, 'brand': brand.name or '-', 'type': description,
                'year': year, 'plate': line._rental_invoice_license_plate() or 'TBA',
                'start': self._get_local_date(line.actual_delivery_date) or self.contract_start_date,
                'end': self.contract_end_date,
                'dpp': amount(details['total_excluded_currency']),
                'ppn': amount(ppn), 'pph': amount(pph),
                'total': amount(details['total_included_currency']),
                'location': self.location_id.name or '-',
            })
        for row in rows:
            for key in ('start', 'end'):
                row[key] = row[key].strftime('%d-%m-%Y') if row[key] else '-'
        return {
            'appendix_contract_date': start_label,
            'appendix_contract_date_upper': start_label.upper(),
            'appendix_payment_frequency': frequency,
            'appendix_payment_terms': self.payment_term_id.name or '-',
            'appendix_vehicle_rows': rows,
        }
