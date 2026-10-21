import calendar
import logging
import re
from collections import defaultdict

from dateutil.relativedelta import relativedelta

from odoo import Command, fields, models, _
from odoo.exceptions import UserError
from odoo.tools import SQL, float_compare


_logger = logging.getLogger(__name__)

_RPC_DESCRIPTION_PREFIX = re.compile(
    r'^[ \t]*RPC/\d{4}/\d{2}[-/]\d+(?!\w)[ \t]*(?:[-–—:][ \t]*)?',
    re.IGNORECASE,
)
_LICENSE_PLATE = re.compile(r'^[A-Z]{1,2}\s*\d{1,4}\s*[A-Z]{0,3}$', re.IGNORECASE)


def _without_rpc_description_prefix(description):
    """Remove generated RPC references, retaining product text and user notes."""
    result = []
    changed = False
    for paragraph in (description or '').splitlines():
        cleaned = _RPC_DESCRIPTION_PREFIX.sub('', paragraph)
        changed |= cleaned != paragraph
        if cleaned != paragraph and not cleaned.strip():
            continue
        result.append(cleaned)
    return '\n'.join(result).strip() if changed else (description or '')


class LegacyBillingInvoiceMismatch(UserError):
    """Only an existing, unlinked invoice can cause this reconciliation error."""


class BillingEngineRegenerationPending(UserError):
    """Do not invoice a forecast awaiting its explicit one-time regeneration."""


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def _billing_engine_invoice_group_key(self, row):
        self.ensure_one()
        delivery_key = (
            (row.rental_start.month, row.rental_start.day)
            if self.grouping_invoice == 'delivered_date' and row.rental_start else False
        )
        # A revised forecast must never append units to an earlier-policy draft.
        return (row.period_start, row.period_end, delivery_key, row.billing_revision)

    def _link_existing_billing_engine_invoices(self):
        """Adopt an exact legacy match; never silently rebill an ambiguous invoice."""
        self.ensure_one()
        rows = self.billing_engine_line_ids.sudo()
        invoices = self.order_line.invoice_lines.move_id.filtered(
            lambda move: move.move_type == 'out_invoice' and move.state != 'cancel'
        )
        linked_invoices = rows.invoice_id
        for invoice in invoices - linked_invoices:
            if not invoice.x_is_rental_invoice:
                raise LegacyBillingInvoiceMismatch(_(
                    'Rental Order %s already has an invoice outside Billing Engine '
                    '(%s). Review it before generating additional rental invoices.',
                    self.name, invoice.display_name,
                ))
            matched = self.env['sale.order.billing.engine']
            for line in invoice.invoice_line_ids.filtered(lambda item: item.display_type == 'product'):
                candidates = rows.filtered(
                    lambda row: not row.invoice_id and row.sale_line_id in line.sale_line_ids
                    and row.period_start == invoice.x_rental_period_start
                    and row.period_end == invoice.x_rental_period_end
                    and not float_compare(
                        row.amount, line.price_unit * line.quantity * (1 - line.discount / 100),
                        precision_rounding=self.currency_id.rounding,
                    )
                )
                if len(candidates) == 1:
                    candidates.write({'invoice_id': invoice.id, 'invoice_line_id': line.id})
                    matched |= candidates
            source_lines = invoice.invoice_line_ids.filtered(
                lambda line: line.display_type == 'product' and line.sale_line_ids & self.order_line
            )
            if len(matched) != len(source_lines):
                raise LegacyBillingInvoiceMismatch(_(
                    'Invoice %s for Rental Order %s does not match the current Billing '
                    'Engine periods and amounts. Review the existing invoice before '
                    'generating again to avoid duplicate billing.',
                    invoice.display_name, self.name,
                ))

    def _prepare_billing_engine_invoice_line(self, row):
        self.ensure_one()
        line = row.sale_line_id
        plate = line._rental_invoice_license_plate()
        description = '%s\n%s\n%s - %s' % (
            _without_rpc_description_prefix(line.name) or row.product_id.display_name,
            plate or '-',
            row.rental_start.strftime('%d-%m-%Y'), row.rental_end.strftime('%d-%m-%Y'),
        )
        values = line._prepare_invoice_line(
            name=description,
            quantity=1.0,
            price_unit=row.amount,
            discount=0.0,
            extra_tax_data=False,
            x_plate_number=plate,
            x_billing_month=self._compute_billing_month_str(line, row.period_start),
        )
        line._set_analytic_distribution(values)
        return values

    def _generate_billing_engine_invoices(self, orders=None, today=None, due_only=False,
                                        current_month_only=True, skip_report=None,
                                        batch_months=0):
        """Create draft invoices atomically from accessible, unlinked engine rows.

        The manual wizard takes six months of period starts, beginning with
        each order's earliest eligible uninvoiced period, without today's date
        cutoff. Complete frequency periods are never split. Cron keeps Invoice
        Draft <= today without this batch limit, so preparation lead time still
        works across month boundaries. Neither entry point posts invoices.
        """
        self.env['account.move'].check_access('create')
        if batch_months and (type(batch_months) is not int or batch_months < 0):
            raise UserError(_('The invoice batch size must be a positive number of months.'))
        today = fields.Date.to_date(today or fields.Date.context_today(self))
        month_end = today.replace(day=calendar.monthrange(today.year, today.month)[1])
        orders = orders if orders is not None else self
        if not orders:
            orders = self.search([
                ('is_rental_order', '=', True), ('state', 'in', ('sale', 'done')),
                ('company_id', 'in', self.env.companies.ids),
            ])
        orders.check_access('read')
        orders = orders.filtered(lambda order: order.is_rental_order and order.state in ('sale', 'done'))
        result = self.env['account.move']
        for order in orders.sorted('id'):
            try:
                # Rolling back a skipped order also removes any partial legacy
                # links or schedule changes; valid orders can still be committed.
                with self.env.cr.savepoint():
                    generated = order._generate_billing_engine_order_invoices(
                        today, month_end, due_only, current_month_only,
                        batch_months=batch_months,
                    )
            except (LegacyBillingInvoiceMismatch, BillingEngineRegenerationPending) as error:
                reason = str(error)
                if skip_report is not None:
                    skip_report.append({
                        'order_id': order.id, 'order_name': order.name,
                        'reason': reason,
                    })
                _logger.warning('Skipped Rental Order %s: %s', order.name, reason)
                continue
            result |= generated
        return result

    def _generate_billing_engine_order_invoices(self, today, month_end, due_only,
                                              current_month_only, batch_months=0):
        """Process one order; unrelated validation/security errors still propagate."""
        self.ensure_one()
        result = self.env['account.move']
        for order in self:
            # Serialize manual/cron requests for each order. Creation plus links
            # commit together, so a second request sees the already linked rows.
            self.env.cr.execute(SQL(
                'SELECT id FROM sale_order WHERE id = %s FOR UPDATE', order.id,
            ))
            order.invalidate_recordset()
            if not order.is_rental_order or order.state not in ('sale', 'done'):
                continue
            if order.billing_settings_changed and not order.billing_engine_regenerated:
                raise BillingEngineRegenerationPending(_(
                    'Rental Order %s has revised billing settings. Click Generate '
                    'Billing Engine on that order before generating invoices.', order.name,
                ))
            order._sync_billing_engine()
            rows = self.env['sale.order.billing.engine'].search([('order_id', '=', order.id)])
            rows.invalidate_recordset()
            if not rows.filtered(
                lambda row: not row.invoice_id and row.rental_start and row.invoice_date
                and (not current_month_only or row.invoice_date <= month_end)
                and (not due_only or row.invoice_draft_date and row.invoice_draft_date <= today)
            ):
                continue
            order._link_existing_billing_engine_invoices()
            pending = rows.filtered(
                lambda row: not row.invoice_id and row.rental_start and row.rental_end
                and row.invoice_date and row.sale_line_id.product_uom_qty > 0
                and not row.sale_line_id.is_downpayment
                and (not current_month_only or row.invoice_date <= month_end)
                and (not due_only or row.invoice_draft_date and row.invoice_draft_date <= today)
            )
            if pending and batch_months:
                # Select only after legacy reconciliation and under the order
                # lock. Existing invoices, gaps and late units therefore cannot
                # be skipped by a saved counter or an outdated batch boundary.
                first_period = min(pending.mapped('period_start'))
                batch_end = first_period + relativedelta(months=batch_months)
                pending = pending.filtered(lambda row: row.period_start < batch_end)
            groups = defaultdict(lambda: self.env['sale.order.billing.engine'])
            for row in pending:
                groups[order._billing_engine_invoice_group_key(row)] |= row
            for key, group in groups.items():
                invoice_date = min(group.mapped('invoice_date'))
                existing = rows.filtered(
                    lambda row: row.invoice_id and order._billing_engine_invoice_group_key(row) == key
                    and row.invoice_id.state == 'draft'
                ).invoice_id
                if len(existing) > 1:
                    raise UserError(_(
                        'More than one draft invoice exists for the same billing group '
                        'on %s. Review those drafts before generating again.', order.name,
                    ))
                if existing and existing.invoice_date != invoice_date:
                    raise UserError(_(
                        'The invoice date for billing group %s on %s differs from its '
                        'existing draft invoice. Review the draft and order settings '
                        'before adding more units.', group[0].period, order.name,
                    ))
                prepared_lines = [
                    order.with_company(order.company_id)._prepare_billing_engine_invoice_line(row)
                    for row in group
                ]
                if existing:
                    invoice = existing
                    invoice.write({'invoice_line_ids': [Command.create(vals) for vals in prepared_lines]})
                else:
                    values = order.with_company(order.company_id)._prepare_invoice()
                    values.update({
                        'state': 'draft',
                        'invoice_date': invoice_date,
                        'x_is_rental_invoice': True,
                        'x_rental_period_start': key[0],
                        'x_rental_period_end': key[1],
                        'x_rental_delivery_date': (
                            group[0].sale_line_id.actual_delivery_date
                            if order.grouping_invoice == 'delivered_date' else False
                        ),
                        'invoice_line_ids': [Command.create(vals) for vals in prepared_lines],
                    })
                    invoice = self.env['account.move'].with_company(order.company_id).create(values)
                    order._add_billing_engine_stamp_duty(invoice)
                for row in group:
                    invoice_line = invoice.invoice_line_ids.filtered(
                        lambda line: row.sale_line_id in line.sale_line_ids
                        and line.id not in rows.invoice_line_id.ids
                    )
                    if len(invoice_line) != 1:
                        raise UserError(_('Cannot uniquely link an invoice line to its Billing Engine row.'))
                    row.sudo().write({'invoice_id': invoice.id, 'invoice_line_id': invoice_line.id})
                group.sale_line_id._update_invoice_tracking()
                result |= invoice
        return result

    def _add_billing_engine_stamp_duty(self, invoice):
        """Only new engine invoices: no retrofit or duplicate on late-unit append."""
        self.ensure_one()
        product = self.company_id.rental_invoice_stamp_product_id.with_company(self.company_id)
        if not product or invoice.invoice_line_ids.filtered('x_is_stamp_duty'):
            return
        if product.company_id and product.company_id != self.company_id:
            raise UserError(_('The stamp duty product must belong to the Rental Order company.'))
        if not product.active or product.type != 'service' or not product.sale_ok:
            raise UserError(_('Configure an active sales service product for stamp duty in Accounting settings.'))
        account = product.product_tmpl_id.get_product_accounts(fiscal_pos=invoice.fiscal_position_id)['income']
        if not account:
            raise UserError(_('Configure the stamp duty product income account before generating invoices.'))
        taxes = product.taxes_id.filtered(lambda tax: tax.company_id == self.company_id)
        taxes = invoice.fiscal_position_id.map_tax(taxes)
        if invoice.currency_id != self.env.ref('base.IDR'):
            raise UserError(_('Automatic stamp duty currently supports IDR invoices only.'))
        amount = 10000
        invoice.write({'invoice_line_ids': [Command.create({
            'product_id': product.id, 'name': _('Biaya Materai'),
            'account_id': account.id, 'quantity': 1, 'price_unit': amount,
            'product_uom_id': product.uom_id.id, 'tax_ids': [Command.set(taxes.ids)],
            'x_is_stamp_duty': True, 'sequence': 9999,
        })]})

    def _generate_rental_invoices_if_due(self, today, trigger_all=False):
        """All automatic/legacy entry points share the engine and its invoice links."""
        self.ensure_one()
        return self._generate_billing_engine_invoices(
            today=today, due_only=not trigger_all, current_month_only=False,
        )

    def action_simulate_next_cycle_invoice(self):
        self.ensure_one()
        self.check_access('read')
        self._sync_billing_engine()
        rows = self.billing_engine_line_ids.filtered(
            lambda row: not row.invoice_id and row.invoice_draft_date and row.rental_start
        )
        if not rows:
            raise UserError(_('No eligible uninvoiced Billing Engine rows were found.'))
        target = min(rows.mapped('invoice_draft_date'))
        invoices = self._generate_billing_engine_invoices(
            today=target, due_only=True, current_month_only=False,
        )
        return self.action_view_invoice(invoices=invoices)


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    def _rental_invoice_license_plate(self):
        """Never substitute the FN asset identifier for a vehicle registration."""
        self.ensure_one()
        vehicle = self.fleet_vehicle_id
        if vehicle and vehicle.has_access('read') and vehicle.license_plate:
            return vehicle.license_plate
        analytic = self.order_id._get_billing_engine_analytic_account(self)
        if analytic and 'license_plate' in analytic._fields and analytic.license_plate:
            return analytic.license_plate
        vehicles = self.env['fleet.vehicle']
        if analytic and 'analytic_account_id' in vehicles._fields and vehicles.has_access('read'):
            vehicles = vehicles.search([
                ('analytic_account_id', '=', analytic.id),
                ('company_id', 'in', [False, self.company_id.id]),
                ('license_plate', '!=', False),
            ], limit=2)
            if len(vehicles) == 1:
                return vehicles.license_plate
        # Older databases sometimes store the registration as the analytic name.
        name = analytic.name if analytic else ''
        return name if _LICENSE_PLATE.fullmatch(name or '') else False

    def _prepare_invoice_line(self, **optional_values):
        values = super()._prepare_invoice_line(**optional_values)
        # Also cover standard Create Invoice for Rental Orders. The source SO
        # description and RPC relationships remain intact, as do existing invoices.
        if self.order_id.is_rental_order and not self.display_type:
            values['name'] = (
                _without_rpc_description_prefix(values.get('name'))
                or self.product_id.display_name
            )
        return values
