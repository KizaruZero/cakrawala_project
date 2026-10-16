import calendar
import logging
import re
from collections import defaultdict

from odoo import Command, fields, models, _
from odoo.exceptions import UserError
from odoo.tools import SQL, float_compare


_logger = logging.getLogger(__name__)

_RPC_DESCRIPTION_PREFIX = re.compile(
    r'^[ \t]*RPC/\d{4}/\d{2}[-/]\d+(?!\w)[ \t]*(?:[-–—:][ \t]*)?',
    re.IGNORECASE,
)


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
        description = '%s\n%s: %s\n%s - %s' % (
            _without_rpc_description_prefix(line.name) or row.product_id.display_name,
            _('Unit plate No'), row.unit_plate_no or '-',
            row.rental_start, row.rental_end,
        )
        values = line._prepare_invoice_line(
            name=description,
            quantity=1.0,
            price_unit=row.amount,
            discount=0.0,
            extra_tax_data=False,
            x_plate_number=row.unit_plate_no,
            x_billing_month=self._compute_billing_month_str(line, row.period_start),
        )
        line._set_analytic_distribution(values)
        return values

    def _generate_billing_engine_invoices(self, orders=None, today=None, due_only=False,
                                        current_month_only=True, skip_report=None):
        """Create draft invoices atomically from accessible, unlinked engine rows.

        Callers choose their cutoff: the manual Generate Invoices wizard uses
        all periods without either date cutoff. Cron keeps Invoice Draft <=
        today and bypasses the month horizon so preparation lead time still
        works across month boundaries. Neither entry point posts invoices.
        """
        self.env['account.move'].check_access('create')
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
                                              current_month_only):
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
