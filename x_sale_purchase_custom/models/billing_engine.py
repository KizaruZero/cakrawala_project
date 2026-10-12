from datetime import timedelta
import calendar

from babel.dates import format_date
from dateutil.relativedelta import relativedelta

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class SaleOrderBillingEngine(models.Model):
    _name = 'sale.order.billing.engine'
    _description = 'Rental Order Billing Engine'
    _order = 'period_start, order_id, sale_line_id, id'
    _rec_name = 'period'
    _rec_names_search = ['unit_plate_no', 'order_id.name']
    _check_company_auto = True

    order_id = fields.Many2one(
        'sale.order', required=True, readonly=True, index=True,
        ondelete='cascade', check_company=True,
    )
    sale_line_id = fields.Many2one(
        'sale.order.line', required=True, readonly=True, index=True,
        ondelete='cascade', check_company=True,
    )
    company_id = fields.Many2one(related='order_id.company_id', store=True)
    currency_id = fields.Many2one(related='order_id.currency_id', store=True)
    period_start = fields.Date(required=True, readonly=True, index=True)
    period_end = fields.Date(required=True, readonly=True)
    period = fields.Char(string='Period', compute='_compute_period')
    analytic_account_id = fields.Many2one(
        'account.analytic.account', readonly=True, check_company=True,
    )
    unit_plate_no = fields.Char(string='Unit plate No', readonly=True)
    product_id = fields.Many2one(
        'product.product', string='Type', readonly=True, check_company=True,
    )
    rental_start = fields.Date(string='Rental start', readonly=True)
    rental_end = fields.Date(string='Rental end', readonly=True)
    total_days = fields.Integer(string='Total days', readonly=True)
    rate_monthly = fields.Monetary(string='Rate monthly', readonly=True)
    amount = fields.Monetary(string='Amount', readonly=True)
    invoice_date = fields.Date(string='Invoice Date', readonly=True)
    invoice_draft_date = fields.Date(string='Invoice draft', readonly=True)
    invoice_id = fields.Many2one(
        'account.move', readonly=True, copy=False, index=True,
        ondelete='set null', check_company=True,
    )
    invoice_line_id = fields.Many2one(
        'account.move.line', readonly=True, copy=False,
        ondelete='set null', check_company=True,
    )
    invoice_number = fields.Char(
        string='Invoice Number', compute='_compute_invoice_details', store=True,
    )
    invoice_status = fields.Char(
        string='Invoice Status', compute='_compute_invoice_details', store=True,
    )

    @api.depends('invoice_id.name', 'invoice_id.state', 'invoice_id.payment_state',
                 'invoice_id.is_move_sent')
    def _compute_invoice_details(self):
        for row in self:
            invoice = row.invoice_id
            row.invoice_number = (
                invoice.name if invoice and invoice.name not in (False, '/') else False
            )
            labels = dict(invoice._fields['status_in_payment']._description_selection(self.env))
            row.invoice_status = labels.get(invoice.status_in_payment, False) if invoice else False

    _line_period_unique = models.Constraint(
        'UNIQUE(sale_line_id, period_start)',
        'A rental order line can only have one billing row per period.',
    )

    @api.depends_context('lang')
    @api.depends('period_start', 'period_end')
    def _compute_period(self):
        locale = self.env.lang or 'en_US'
        for row in self:
            if not row.period_start or not row.period_end:
                row.period = False
            elif row.period_start.replace(day=1) == row.period_end.replace(day=1):
                row.period = format_date(row.period_start, 'MMM yyyy', locale=locale)
            elif row.period_start.year == row.period_end.year:
                row.period = '%s - %s' % (
                    format_date(row.period_start, 'MMM', locale=locale),
                    format_date(row.period_end, 'MMM yyyy', locale=locale),
                )
            else:
                row.period = '%s - %s' % (
                    format_date(row.period_start, 'MMM yyyy', locale=locale),
                    format_date(row.period_end, 'MMM yyyy', locale=locale),
                )


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    billing_engine_line_ids = fields.One2many(
        'sale.order.billing.engine', 'order_id',
        string='Billing Engine', readonly=True, copy=False,
    )
    billing_engine_count = fields.Integer(compute='_compute_billing_engine_count')

    @api.depends('billing_engine_line_ids')
    def _compute_billing_engine_count(self):
        for order in self:
            order.billing_engine_count = len(order.billing_engine_line_ids)

    @api.model_create_multi
    def create(self, vals_list):
        orders = super().create(vals_list)
        if not self.env.context.get('skip_billing_engine_sync'):
            orders._sync_billing_engine()
        return orders

    def write(self, vals):
        # Re-cutting a billed schedule would create overlapping invoices. Pending
        # prices/dates can still change, but billed rows are immutable snapshots.
        structural_fields = {
            'actual_rental_start_date', 'actual_rental_return_date', 'masa_sewa_bulan',
            'invoicing_cycle_period', 'grouping_invoice', 'consolidate_invoice',
            'currency_id', 'company_id',
        }
        if structural_fields.intersection(vals):
            for order in self:
                changed = any(
                    order._fields[name].convert_to_cache(vals[name], order)
                    != order._fields[name].convert_to_cache(order[name], order)
                    for name in structural_fields.intersection(vals)
                )
                if changed and order.billing_engine_line_ids.invoice_id:
                    raise UserError(_(
                        'The billing frequency, grouping, company, currency and contract '
                        'boundaries cannot be changed after Billing Engine invoices exist '
                        'for %s. Review those invoices first.', order.name,
                    ))
        result = super().write(vals)
        schedule_fields = {
            'state', 'is_rental_order', 'actual_rental_start_date',
            'actual_rental_return_date', 'masa_sewa_bulan',
            'invoicing_cycle_period', 'billing_rule', 'invoicing_date_monthly',
            'top_billing', 'weekend_rule_adjustment', 'invoice_print_lead_time',
            'currency_id', 'company_id', 'grouping_invoice', 'consolidate_invoice',
        }
        if (
            not self.env.context.get('skip_billing_engine_sync')
            and schedule_fields.intersection(vals)
        ):
            self._sync_billing_engine()
        return result

    def action_view_billing_engine(self):
        self.ensure_one()
        self.check_access('read')
        # Also populate schedules for orders confirmed before this feature was installed.
        self._sync_billing_engine()
        action = self.env['ir.actions.actions']._for_xml_id(
            'x_sale_purchase_custom.action_sale_order_billing_engine'
        )
        action['domain'] = [('order_id', '=', self.id)]
        action['context'] = {'default_order_id': self.id}
        action['name'] = _('Billing Engine - %s', self.name)
        return action

    def _get_billing_engine_periods(self):
        """Cover all contract calendar months, including a partial final month."""
        self.ensure_one()
        # Stored schedules must not change when a viewer has a different timezone.
        company_context = self.with_context(tz=self.company_id.partner_id.tz or 'Asia/Jakarta')
        start = (
            fields.Datetime.context_timestamp(company_context, self.actual_rental_start_date).date()
            if self.actual_rental_start_date else False
        )
        end = (
            fields.Datetime.context_timestamp(company_context, self.actual_rental_return_date).date()
            if self.actual_rental_return_date else False
        )
        if not start or not end or end <= start:
            return []

        first_month = start.replace(day=1)
        # Actual To is an exclusive anniversary boundary. A mid-month To still
        # includes that calendar month; a To on the 1st excludes that month.
        last_month = (end - timedelta(days=1)).replace(day=1)
        month_count = (
            (last_month.year - first_month.year) * 12
            + last_month.month - first_month.month + 1
        )
        frequency_months = {
            'monthly': 1,
            'per_3_months': 3,
            'per_6_months': 6,
            'yearly': 12,
            'as_duration': month_count,
        }.get(self.invoicing_cycle_period, 1)
        periods = []
        for offset in range(0, month_count, frequency_months):
            months = min(frequency_months, month_count - offset)
            period_start = first_month + relativedelta(months=offset)
            period_end = period_start + relativedelta(months=months) - timedelta(days=1)
            periods.append((period_start, period_end, months))
        return periods

    def _get_billing_engine_analytic_account(self, line):
        """Read the vehicle analytic account, including native multi-plan keys."""
        self.ensure_one()
        account_ids = []
        for key in (line.analytic_distribution or {}):
            for token in str(key).split(','):
                token = token.strip()
                if token.isdigit() and int(token) not in account_ids:
                    account_ids.append(int(token))
        accounts = self.env['account.analytic.account'].browse(account_ids).exists()
        accounts = accounts.filtered(
            lambda account: not account.company_id or account.company_id == self.company_id
        )
        if 'license_plate' in accounts._fields:
            vehicle_accounts = accounts.filtered('license_plate')
            if vehicle_accounts:
                return vehicle_accounts[:1]
        return accounts[:1]

    def _get_billing_engine_invoice_date(self, period_start, period_end, delivery,
                                       rental_start=None, rental_end=None):
        self.ensure_one()
        if not delivery or not self.top_billing:
            return False
        invoice_month = period_start
        if self.top_billing == 'dibelakang':
            invoice_month = period_end + timedelta(days=1)
        elif delivery > period_start and delivery.replace(day=1) > period_start:
            # A unit delivered later in the first cycle is not billed before its delivery month.
            invoice_month = delivery.replace(day=1)
        day = int(self.invoicing_date_monthly) if self.invoicing_date_monthly else delivery.day
        invoice_date = invoice_month.replace(
            day=min(day, calendar.monthrange(invoice_month.year, invoice_month.month)[1])
        )
        # The first delivery cycle follows the customer's Invoicing Day. Later
        # separate-unit cycles always use the rental boundary plus one day,
        # whether that date is earlier or later than the configured Invoicing Day.
        first_cycle = period_start <= delivery.replace(day=1) <= period_end
        if delivery.replace(day=1) < period_start and self.actual_rental_start_date:
            contract_start = fields.Datetime.context_timestamp(
                self.with_context(tz=self.company_id.partner_id.tz or 'Asia/Jakarta'),
                self.actual_rental_start_date,
            ).date()
            first_cycle = period_start == contract_start.replace(day=1)
        if self.grouping_invoice == 'delivered_date' and not first_cycle:
            anchor = rental_end if self.top_billing == 'dibelakang' else rental_start
            if anchor:
                invoice_date = anchor + timedelta(days=1)
        weekday = invoice_date.weekday()
        if weekday >= 5:
            if self.weekend_rule_adjustment == 'next_working_day':
                invoice_date += timedelta(days=7 - weekday)
            elif self.weekend_rule_adjustment == 'previous_working_day':
                invoice_date -= timedelta(days=weekday - 4)
        return invoice_date

    def _prepare_billing_engine_values(self, line, period_start, period_end, months, analytic=None):
        self.ensure_one()
        if analytic is None:
            analytic = self._get_billing_engine_analytic_account(line)
        plate = False
        if analytic:
            plate = (
                analytic.license_plate if 'license_plate' in analytic._fields else False
            ) or analytic.name
        values = {
            'order_id': self.id,
            'sale_line_id': line.id,
            'period_start': period_start,
            'period_end': period_end,
            'analytic_account_id': analytic.id or False,
            'unit_plate_no': plate,
            'product_id': line.product_id.id,
            'rate_monthly': line.price_unit,
            'rental_start': False,
            'rental_end': False,
            'total_days': 0,
            'amount': 0.0,
            'invoice_date': False,
            'invoice_draft_date': False,
        }
        delivery = line.actual_delivery_date
        if not delivery or delivery > period_end:
            # Keep period rows visible, but never invent actual delivery dates or charges.
            return values

        delivery_month = delivery.replace(day=1)
        first_billable_month = max(period_start, delivery_month)
        billed_months = (
            (period_end.year - first_billable_month.year) * 12
            + period_end.month - first_billable_month.month + 1
        )
        if self.billing_rule == 'full_charge':
            offset = (
                (first_billable_month.year - delivery.year) * 12
                + first_billable_month.month - delivery.month
            )
            rental_start = delivery + relativedelta(months=offset)
            total_days = 30 * billed_months
            rental_end = rental_start + timedelta(days=total_days)
            if months > 1:
                # Multi-month Full cycles follow the workbook's anniversaries:
                # 5 January -> 4 April, rather than a fixed 90-day approximation.
                rental_end = delivery + relativedelta(months=offset + billed_months) - timedelta(days=1)
                total_days = (rental_end - rental_start).days
            amount = line.price_unit * billed_months
        elif self.billing_rule == 'prorate':
            rental_start = max(first_billable_month, delivery)
            rental_end = period_end
            if period_start <= delivery_month <= period_end:
                first_month_end = delivery_month + relativedelta(months=1) - timedelta(days=1)
                first_days = (first_month_end - delivery).days
                calendar_days = calendar.monthrange(delivery.year, delivery.month)[1]
                total_days = first_days + 30 * (billed_months - 1)
                amount = line.price_unit * (first_days / calendar_days + billed_months - 1)
            else:
                total_days = 30 * billed_months
                amount = line.price_unit * billed_months
        else:
            return values

        invoice_date = self._get_billing_engine_invoice_date(
            period_start, period_end, delivery, rental_start, rental_end,
        )
        values.update({
            'rental_start': rental_start,
            'rental_end': rental_end,
            'total_days': total_days,
            'amount': self.currency_id.round(amount),
            'invoice_date': invoice_date,
            'invoice_draft_date': (
                invoice_date - timedelta(days=max(self.invoice_print_lead_time or 0, 0))
                if invoice_date else False
            ),
        })
        return values

    def _sync_billing_engine(self, sale_lines=None):
        """Upsert the forecast only; no account.move or invoice status is generated."""
        if self.env.context.get('skip_billing_engine_sync'):
            return
        # Users can read forecasts; only this order-driven internal operation writes them.
        Engine = self.env['sale.order.billing.engine'].sudo().with_context(
            skip_billing_engine_sync=True,
        )
        # Preserve the last forecast for reference when an order is cancelled or
        # returned to quotation. It is only recalculated while it is a Sales Order.
        for order in self.filtered(
            lambda item: item.is_rental_order and item.state in ('sale', 'done')
        ):
            periods = order._get_billing_engine_periods()
            lines = order.order_line
            if sale_lines is not None:
                lines &= sale_lines
            eligible_lines = lines.filtered(
                lambda line: line.product_id and not line.display_type
                and not line.is_downpayment and line.product_uom_qty > 0
            )
            domain = [('order_id', '=', order.id)]
            if sale_lines is not None:
                domain.append(('sale_line_id', 'in', lines.ids))
            existing = Engine.search(domain)
            by_key = {(row.sale_line_id.id, row.period_start): row for row in existing}
            wanted = set()
            to_create = []
            for line in eligible_lines:
                analytic = order._get_billing_engine_analytic_account(line)
                for period_start, period_end, months in periods:
                    key = (line.id, period_start)
                    wanted.add(key)
                    values = order._prepare_billing_engine_values(
                        line, period_start, period_end, months, analytic=analytic,
                    )
                    row = by_key.get(key)
                    if row:
                        if row.invoice_id:
                            continue
                        changed = {}
                        for name, value in values.items():
                            current = row[name]
                            if row._fields[name].type == 'many2one':
                                current = current.id or False
                            expected = value
                            if row._fields[name].type in ('float', 'monetary'):
                                expected = row._fields[name].convert_to_cache(value, row)
                            if current != expected:
                                changed[name] = value
                        if changed:
                            row.write(changed)
                    else:
                        to_create.append(values)
            obsolete = existing.filtered(
                lambda row: not row.invoice_id
                and (row.sale_line_id.id, row.period_start) not in wanted
            )
            if obsolete:
                obsolete.unlink()
            if to_create:
                Engine.create(to_create)


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)
        lines.order_id._sync_billing_engine(sale_lines=lines)
        return lines

    def write(self, vals):
        previous_orders = self.order_id
        result = super().write(vals)
        source_fields = {
            'actual_delivery_date', 'analytic_distribution', 'product_id',
            'price_unit', 'product_uom_qty', 'display_type', 'is_downpayment',
            'order_id',
        }
        if source_fields.intersection(vals):
            if 'order_id' in vals:
                (previous_orders | self.order_id)._sync_billing_engine()
            else:
                self.order_id._sync_billing_engine(sale_lines=self)
        return result
