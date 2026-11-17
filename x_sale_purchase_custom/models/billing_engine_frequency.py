from datetime import timedelta

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError
from odoo.tools import SQL

from .billing_engine import BILLING_AMENDMENT_FIELDS


_TOKEN = object()
_FREQUENCIES = {'monthly': 1, 'per_3_months': 3, 'per_6_months': 6, 'yearly': 12, 'as_duration': 0}


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    billing_frequency_revision = fields.Integer(
        readonly=True, copy=False, tracking=True,
        help='System-managed revision of remaining billing periods after a frequency amendment.',
    )

    @api.model_create_multi
    def create(self, values_list):
        if any('billing_frequency_revision' in values for values in values_list):
            raise UserError(_('Billing frequency revisions are managed by the system.'))
        return super().create(values_list)

    def write(self, values):
        if 'billing_frequency_revision' in values and self.env.context.get('_billing_frequency_token') is not _TOKEN:
            raise UserError(_('Billing frequency revisions cannot be changed manually.'))
        if 'invoicing_cycle_period' not in values:
            return super().write(values)
        self.check_access('write')
        with self.env.cr.savepoint():
            self._lock_billing_engine_orders()
            amended = self.filtered(lambda order: order.is_rental_order
                                    and order.invoicing_cycle_period != values['invoicing_cycle_period'])
            if amended.filtered(lambda order: order.state in ('done', 'cancel')):
                raise UserError(_('Invoicing Frequency can only be amended on an active Rental Sales Order.'))
            amended = amended.filtered(lambda order: order.state == 'sale')
            if amended and values['invoicing_cycle_period'] not in _FREQUENCIES:
                raise UserError(_('Select a valid Invoicing Frequency.'))
            amended = amended.filtered(lambda order: order.billing_frequency_revision
                or order.billing_engine_line_ids.invoice_id or order.billing_engine_line_ids.invoice_line_id
                or order.order_line.invoice_lines.move_id.filtered(lambda invoice: invoice.state != 'cancel'))
            if not amended:
                return super().write(values)
            for order in amended:
                if order.company_id not in self.env.companies:
                    raise AccessError(_('Activate the Rental Order company before changing Invoicing Frequency.'))
                if order.billing_settings_changed and not order.billing_engine_regenerated:
                    raise UserError(_('Complete the pending Generate Billing Engine action before changing Invoicing Frequency.'))
                if 'order_line' in values:
                    raise UserError(_('Save rental unit/price changes separately from Invoicing Frequency.'))
                if any(order[name] != order._fields[name].convert_to_cache(values[name], order)
                       for name in BILLING_AMENDMENT_FIELDS.intersection(values)):
                    raise UserError(_('Save changes to TOP/Grouping Invoice/Invoicing Day separately from Invoicing Frequency.'))
                structural = {'state', 'is_rental_order', 'actual_rental_start_date',
                              'actual_rental_return_date', 'masa_sewa_bulan', 'billing_rule',
                              'currency_id', 'company_id', 'consolidate_invoice'}
                if any(order._fields[name].convert_to_cache(order[name], order)
                       != order._fields[name].convert_to_cache(values[name], order)
                       for name in structural.intersection(values)):
                    raise UserError(_('Change only Invoicing Frequency, not contract/company/calculation boundaries, in this save.'))
                order._prepare_billing_frequency_amendment()
            # Do not let the old calendar-wide sync run in between changing the
            # frequency and sealing the new per-unit policy revision.
            result = super(SaleOrder, self.with_context(skip_billing_engine_sync=True)).write(values)
            for order in amended:
                super(SaleOrder, order.with_context(
                    skip_billing_engine_sync=True, _billing_frequency_token=_TOKEN,
                )).write({'billing_frequency_revision': order.billing_frequency_revision + 1})
                order.with_context(skip_billing_engine_sync=False)._sync_billing_engine()
                order.message_post(body=_(
                    'Invoicing Frequency changed. Affected draft invoices were cancelled; '
                    'remaining Billing Engine periods were rebuilt per unit. Posted invoices were retained. '
                    'Use Generate Invoices to create replacement draft invoices.'))
            if not self.env.context.get('skip_billing_engine_sync'):
                (self - amended)._sync_billing_engine()
            return result

    def _prepare_billing_frequency_amendment(self):
        self.ensure_one()
        # Reconcile historical invoices against the OLD schedule before touching
        # it. Unknown/ambiguous history must never be silently invoiced twice.
        self._link_existing_billing_engine_invoices()
        rows = self.billing_engine_line_ids.sudo()
        # Engine maintenance may sudo, but cancelling accounting documents must
        # always retain the requesting user's native ACLs and workflow checks.
        invoices = self.env['account.move'].browse((rows.invoice_id | rows.invoice_line_id.move_id).ids)
        if invoices.filtered(lambda invoice: invoice.move_type != 'out_invoice'):
            raise UserError(_('Billing Engine links must refer to customer invoices. Review the invoice links.'))
        if invoices:
            invoices.check_access('read')
            invoices.flush_recordset()
            self.env.cr.execute(SQL('SELECT id FROM account_move WHERE id IN %s ORDER BY id FOR UPDATE',
                                    tuple(invoices.ids)))
            invoices.invalidate_recordset()
        drafts = invoices.filtered(lambda invoice: invoice.state == 'draft')
        for invoice in drafts:
            invoice.check_access('write')
            other_rows = self.env['sale.order.billing.engine'].sudo().search([
                '|', ('invoice_id', '=', invoice.id), ('invoice_line_id.move_id', '=', invoice.id),
                ('order_id', '!=', self.id),
            ], limit=1)
            if other_rows or invoice.invoice_line_ids.sale_line_ids.order_id - self:
                raise UserError(_('Draft invoice %s also contains another order. Review/split it before changing frequency.', invoice.display_name))
            unrelated = invoice.invoice_line_ids.filtered(lambda item: item.display_type == 'product'
                         and not item.sale_line_ids and not item.x_is_stamp_duty)
            if unrelated:
                raise UserError(_('Draft invoice %s contains manually added items. Review it before changing frequency.', invoice.display_name))
            if invoice.matched_payment_ids or invoice.line_ids.matched_debit_ids or invoice.line_ids.matched_credit_ids:
                raise UserError(_('Draft invoice %s has payment/reconciliation activity. Review it before changing frequency.', invoice.display_name))
            # Native cancellation enforces Accounting access and active voucher /
            # fiscal restrictions; never sudo or reset a Posted invoice here.
            invoice.button_cancel()
            invoice.with_context(_billing_frequency_token=_TOKEN).write({
                'billing_frequency_superseded': True,
            })
        rows.invalidate_recordset()
        for row in rows:
            if row.invoice_id and row.invoice_line_id and row.invoice_id != row.invoice_line_id.move_id:
                raise UserError(_('Billing Engine has inconsistent invoice links. Review it before changing frequency.'))
        unposted = rows.filtered(lambda row: (row.invoice_id or row.invoice_line_id.move_id).state != 'posted')
        unposted.unlink()

    def _get_billing_engine_revision(self):
        return super()._get_billing_engine_revision() + 2 * self.billing_frequency_revision

    def _get_billing_engine_line_periods(self, line):
        if not self.billing_frequency_revision:
            return super()._get_billing_engine_line_periods(line)
        monthly = []
        for start, end, months in self._get_billing_engine_periods():
            for offset in range(months):
                month = start + relativedelta(months=offset)
                monthly.append((month, month + relativedelta(months=1) - timedelta(days=1), 1))
        protected = self.billing_engine_line_ids.sudo().filtered(
            lambda row: row.sale_line_id == line and (row.invoice_id or row.invoice_line_id))
        cursor = 0
        if protected:
            # Return corrections are operational only. Preserve the coverage of
            # invoices issued before return, including future linked invoices.
            ignore_return = bool(protected.filtered('invoiced_rental_end') or protected.filtered(
                lambda row: line.bastk_return_date and row.rental_start
                and row.rental_start > line.bastk_return_date))
            atoms = []
            for index, period in enumerate(monthly):
                value = self._prepare_billing_engine_values(line, *period, ignore_return_date=ignore_return)
                if value and value['rental_start'] and value['rental_end']:
                    atoms.append((index, value['rental_start'], value['rental_end']))
            consumed = 0
            for row in protected.sorted(lambda row: (row.rental_start or row.period_start, row.id)):
                if (not row.rental_start or not row.rental_end or consumed >= len(atoms)
                        or atoms[consumed][1] != row.rental_start):
                    raise UserError(_('Invoiced rental periods for unit %s do not form a contiguous contract prefix. Review dates/older invoices before changing or regenerating frequency.', line.display_name))
                end = next((pos for pos in range(consumed, len(atoms))
                            if atoms[pos][2] == (row.invoiced_rental_end or row.rental_end)), None)
                if end is None:
                    raise UserError(_('Invoiced rental dates for unit %s do not match full monthly rental boundaries. Review the posted/manual dates before changing frequency.', line.display_name))
                cursor = atoms[end][0] + 1
                consumed = end + 1
        remaining = monthly[cursor:]
        size = _FREQUENCIES.get(self.invoicing_cycle_period, 1) or max(len(remaining), 1)
        periods = []
        for offset in range(0, len(remaining), size):
            group = remaining[offset:offset + size]
            if group[0][0] in protected.mapped('period_start'):
                raise UserError(_('A retained invoice conflicts with a new period key. Review manually edited Billing Engine dates.'))
            periods.append((group[0][0], group[-1][1], len(group)))
        return periods

    @api.onchange('invoicing_cycle_period')
    def _onchange_billing_frequency_amendment_warning(self):
        if self._origin and self.state == 'sale' and self.is_rental_order and (
                self.invoicing_cycle_period != self._origin.invoicing_cycle_period):
            return {'warning': {'title': _('Change Invoicing Frequency'), 'message': _(
                'Saving cancels affected draft invoices and rebuilds remaining Billing Engine periods. '
                'Posted invoices remain unchanged. Generate replacement invoices separately.')}}


class AccountMove(models.Model):
    _inherit = 'account.move'

    billing_frequency_superseded = fields.Boolean(
        string='Replaced by Billing Frequency Amendment', readonly=True, copy=False, tracking=True,
        help='Cancelled rental draft retained for audit only; generate its replacement from Billing Engine.',
    )

    @api.model_create_multi
    def create(self, values_list):
        if any(values.get('billing_frequency_superseded') for values in values_list):
            raise UserError(_('Only a Billing Engine frequency amendment can replace an invoice.'))
        return super().create(values_list)

    def write(self, values):
        if ('billing_frequency_superseded' in values
                and self.env.context.get('_billing_frequency_token') is not _TOKEN):
            raise UserError(_('The replaced-invoice flag cannot be changed manually.'))
        return super().write(values)

    def _check_billing_frequency_not_superseded(self):
        if self.filtered('billing_frequency_superseded'):
            raise UserError(_(
                'This rental draft was cancelled after an Invoicing Frequency change. '
                'Generate its replacement from Billing Engine; do not reactivate the old invoice.'))

    def button_draft(self):
        self._check_billing_frequency_not_superseded()
        return super().button_draft()

    def _post(self, soft=True):
        self._check_billing_frequency_not_superseded()
        return super()._post(soft=soft)
