from datetime import date, datetime
from unittest.mock import patch

from lxml import etree

from odoo import Command
from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged
from odoo.tests.common import new_test_user

from .test_billing_engine_invoices import RentalBillingEngineInvoiceCommon


@tagged('post_install', '-at_install')
class TestBillingFrequencyAmendment(RentalBillingEngineInvoiceCommon):
    def _all_invoices(self, order):
        return order._generate_billing_engine_invoices(current_month_only=False)

    def _posted_snapshot(self, invoice):
        # Compare stored relations, not context/user-dependent display labels.
        return (invoice.read(['state', 'name', 'invoice_date', 'amount_total', 'invoice_line_ids'], load=None),
                invoice.line_ids.read(['name', 'balance', 'amount_currency', 'account_id',
                                       'tax_ids', 'analytic_distribution'], load=None))

    def _post_first(self, order, count=1):
        self._all_invoices(order)
        rows = self._rows(order)
        invoices = rows[:count].invoice_id
        invoices.action_post()
        return invoices, rows[:count]

    def test_monthly_to_quarterly_keeps_january_and_cancels_only_future_drafts(self):
        order = self._order(months=12)
        posted, retained = self._post_first(order)
        before = self._posted_snapshot(posted)
        old_drafts = (self._rows(order) - retained).invoice_id
        order.invoicing_cycle_period = 'per_3_months'
        self.assertEqual(self._posted_snapshot(posted), before)
        self.assertEqual(set(old_drafts.mapped('state')), {'cancel'})
        rows = self._rows(order)
        self.assertEqual(rows[:1], retained)
        self.assertEqual(rows.mapped('period_start'), [date(2026, m, 1) for m in (1, 2, 5, 8, 11)])
        self.assertEqual(rows.mapped('amount'), [3000000, 9000000, 9000000, 9000000, 6000000])
        self.assertEqual(rows[1].rental_start, retained.rental_end.replace(day=5))
        self.assertFalse(rows[1:].invoice_id)
        self.assertEqual(sum(rows.mapped('amount')), 36000000)
        self.assertEqual(order.billing_frequency_revision, 1)
        new = self._all_invoices(order)
        self.assertEqual(len(new), 4)
        self.assertEqual(set(new.mapped('state')), {'draft'})
        self.assertFalse(self._all_invoices(order))
        self.assertEqual(self._posted_snapshot(posted), before)

    def test_fully_posted_yearly_contract_does_not_create_extra_monthly_billing(self):
        order = self._order(months=12, invoicing_cycle_period='yearly')
        posted, retained = self._post_first(order)
        before = self._posted_snapshot(posted)
        order.invoicing_cycle_period = 'monthly'
        self.assertEqual(self._rows(order), retained)
        self.assertFalse(self._all_invoices(order))
        self.assertEqual(self._posted_snapshot(posted), before)

    def test_posted_year_keeps_full_coverage_before_monthly_remainder(self):
        order = self._order(months=36, invoicing_cycle_period='yearly')
        posted, retained = self._post_first(order)
        before = self._posted_snapshot(posted)
        order.invoicing_cycle_period = 'monthly'
        rows = self._rows(order)
        self.assertEqual(len(rows), 25)
        self.assertEqual(rows[0], retained)
        self.assertEqual(rows[1].rental_start, date(2027, 1, 5))
        self.assertEqual(sum(rows.mapped('amount')), 108000000)
        self.assertEqual(self._posted_snapshot(posted), before)

    def test_month_end_anniversary_survives_frequency_amendment(self):
        order = self._order(months=6, delivery=date(2026, 1, 31))
        posted, retained = self._post_first(order)
        order.invoicing_cycle_period = 'per_3_months'
        rows = self._rows(order)
        self.assertEqual(rows[0], retained)
        self.assertEqual(rows[1].rental_start, date(2026, 2, 28))
        self.assertEqual(rows[1].rental_end, date(2026, 5, 30))
        self.assertEqual(rows[2].rental_start, date(2026, 5, 31))
        self.assertEqual(rows[2].rental_end, date(2026, 7, 30))
        self.assertEqual(sum(rows.mapped('amount')), 18000000)

    def test_yearly_draft_replaced_by_twelve_uninvoiced_monthly_rows(self):
        order = self._order(months=12, invoicing_cycle_period='yearly')
        old = self._all_invoices(order)
        order.invoicing_cycle_period = 'monthly'
        self.assertEqual(old.state, 'cancel')
        self.assertEqual(len(self._rows(order)), 12)
        self.assertFalse(self._rows(order).invoice_id)
        self.assertEqual(sum(self._rows(order).mapped('amount')), 36000000)

    def test_replaced_cancelled_invoice_cannot_be_reactivated_or_posted(self):
        order = self._order(months=6)
        old = self._all_invoices(order)[:1]
        order.invoicing_cycle_period = 'per_3_months'
        self.assertTrue(old.billing_frequency_superseded)
        with self.assertRaisesRegex(UserError, 'do not reactivate'):
            old.button_draft()
        with self.assertRaisesRegex(UserError, 'do not reactivate'):
            old._post()
        self.assertEqual(old.state, 'cancel')
        with self.assertRaises(UserError):
            old.billing_frequency_superseded = False
        with self.assertRaises(UserError):
            old.with_context(_billing_frequency_token=True).write({'billing_frequency_superseded': False})
        self.assertTrue(old.billing_frequency_superseded)
        self.assertFalse(old.copy().billing_frequency_superseded)

    def test_each_unit_restarts_after_its_own_posted_coverage(self):
        order = self._order(months=8, grouping_invoice='delivered_date', order_line=[
            Command.create(self._line_values(date(2026, 1, 5))),
            Command.create(self._line_values(date(2026, 1, 16))),
        ])
        self._all_invoices(order)
        a, b = order.order_line
        first = self._rows(order).filtered(lambda row: row.sale_line_id == a and row.period_start.month == 1)
        second = self._rows(order).filtered(lambda row: row.sale_line_id == b and row.period_start.month <= 2)
        posted = (first | second).invoice_id
        posted.action_post()
        before = self._posted_snapshot(posted)
        order.invoicing_cycle_period = 'per_3_months'
        pending_a = self._rows(order).filtered(lambda row: row.sale_line_id == a and not row.invoice_id)
        pending_b = self._rows(order).filtered(lambda row: row.sale_line_id == b and not row.invoice_id)
        self.assertEqual(pending_a.mapped('period_start'), [date(2026, m, 1) for m in (2, 5, 8)])
        self.assertEqual(pending_b.mapped('period_start'), [date(2026, m, 1) for m in (3, 6)])
        self.assertEqual(pending_a[0].rental_start, date(2026, 2, 5))
        self.assertEqual(pending_b[0].rental_start, date(2026, 3, 16))
        self.assertEqual(self._posted_snapshot(posted), before)
        self.assertEqual(len(self._all_invoices(order)), 5)

    def test_frequency_can_change_repeatedly_without_resetting_other_once_flags(self):
        order = self._order(months=12)
        posted, retained = self._post_first(order)
        order.invoicing_cycle_period = 'per_3_months'
        intermediate = self._all_invoices(order)
        order.invoicing_cycle_period = 'per_6_months'
        self.assertEqual(set(intermediate.mapped('state')), {'cancel'})
        self.assertEqual(self._rows(order).mapped('period_start'), [date(2026, m, 1) for m in (1, 2, 8)])
        self.assertEqual(order.billing_frequency_revision, 2)
        self.assertFalse(order.billing_settings_changed)
        self.assertFalse(order.billing_engine_regenerated)
        self.assertEqual(retained.invoice_id, posted)

    def test_existing_once_amendment_allowance_already_used_does_not_block_frequency(self):
        order = self._order(months=6)
        order.top_billing = 'dibelakang'
        order.action_generate_billing_engine()
        self._post_first(order)
        order.invoicing_cycle_period = 'per_3_months'
        self.assertTrue(order.billing_engine_regenerated)
        self.assertTrue(order.billing_settings_changed)
        with self.assertRaises(UserError):
            order.top_billing = 'didepan'

    def test_pending_once_amendment_must_be_completed_first(self):
        order = self._order(months=6)
        self._post_first(order)
        order.top_billing = 'dibelakang'
        with self.assertRaisesRegex(UserError, 'Complete the pending'):
            order.invoicing_cycle_period = 'per_3_months'

    def test_draft_policy_rows_survive_sync_and_posting_out_of_sequence(self):
        order = self._order(months=12)
        self._post_first(order)
        order.invoicing_cycle_period = 'per_3_months'
        self._all_invoices(order)
        rows = self._rows(order)
        rows[2].invoice_id.action_post()
        before = rows.read(['period_start', 'period_end', 'rental_start', 'rental_end', 'amount', 'invoice_id'])
        order._sync_billing_engine()
        self.assertEqual(self._rows(order).read(list(before[0])), before)
        self.assertFalse(self._all_invoices(order))

    def test_noncontiguous_posted_history_rolls_back_draft_cancellations_and_header(self):
        order = self._order(months=6)
        self._all_invoices(order)
        rows = self._rows(order)
        rows[1].invoice_id.action_post()
        before = rows.read(['invoice_id', 'period_start', 'period_end', 'amount'])
        drafts = rows.invoice_id.filtered(lambda invoice: invoice.state == 'draft')
        with self.assertRaisesRegex(UserError, 'contiguous contract prefix'):
            order.invoicing_cycle_period = 'per_3_months'
        self.assertEqual(order.invoicing_cycle_period, 'monthly')
        self.assertFalse(order.billing_frequency_revision)
        self.assertEqual(set(drafts.mapped('state')), {'draft'})
        self.assertEqual(rows.read(list(before[0])), before)

    def test_manual_posted_dates_cannot_be_silently_recut(self):
        order = self._order(months=6)
        first = self._rows(order)[:1]
        first.rental_end = date(2026, 1, 20)
        self._all_invoices(order)
        first.invoice_id.action_post()
        with self.assertRaisesRegex(UserError, 'monthly rental boundaries'):
            order.invoicing_cycle_period = 'per_3_months'
        self.assertEqual(first.invoice_id.state, 'posted')

    def test_draft_containing_another_order_is_not_cancelled(self):
        order, other = self._order(months=6), self._order(months=6)
        self._all_invoices(order)
        invoice = self._rows(order)[0].invoice_id
        invoice.invoice_line_ids[0].sale_line_ids |= other.order_line
        with self.assertRaisesRegex(UserError, 'another order'):
            order.invoicing_cycle_period = 'per_3_months'
        self.assertEqual(invoice.state, 'draft')
        self.assertEqual(order.invoicing_cycle_period, 'monthly')

    def test_manual_draft_items_require_review_instead_of_disappearing(self):
        order = self._order(months=6)
        invoice = self._all_invoices(order)[:1]
        invoice.write({'invoice_line_ids': [Command.create({
            'name': 'Manual unrelated item', 'quantity': 1, 'price_unit': 10,
            'account_id': self.income_account.id, 'tax_ids': [Command.clear()],
        })]})
        with self.assertRaisesRegex(UserError, 'manually added items'):
            order.invoicing_cycle_period = 'per_3_months'
        self.assertEqual(invoice.state, 'draft')

    def test_native_cancellation_failure_rolls_back_everything(self):
        order = self._order(months=6)
        drafts = self._all_invoices(order)
        original_ids = self._rows(order).ids
        with patch.object(type(drafts), 'button_cancel', side_effect=UserError('Native accounting workflow restriction')):
            with self.assertRaisesRegex(UserError, 'Native accounting'):
                order.invoicing_cycle_period = 'per_3_months'
        self.assertEqual(order.invoicing_cycle_period, 'monthly')
        self.assertEqual(self._rows(order).ids, original_ids)
        self.assertEqual(set(drafts.mapped('state')), {'draft'})

    def test_sales_user_cannot_cancel_invoices_via_sudo_engine(self):
        user = new_test_user(self.env, login='frequency_sales', groups='sales_team.group_sale_salesman',
                             company_id=self.company.id)
        order = self._order(months=6, user_id=user.id)
        drafts = self._all_invoices(order)
        with self.assertRaises(AccessError):
            order.with_user(user).write({'invoicing_cycle_period': 'per_3_months'})
        self.assertEqual(set(drafts.mapped('state')), {'draft'})
        self.assertEqual(order.invoicing_cycle_period, 'monthly')

    def test_finance_user_can_amend_with_native_access(self):
        user = new_test_user(self.env, login='frequency_finance',
                             groups='sales_team.group_sale_salesman,account.group_account_invoice',
                             company_id=self.company.id)
        order = self._order(months=6, user_id=user.id)
        drafts = self._all_invoices(order)
        order.with_user(user).write({'invoicing_cycle_period': 'per_3_months'})
        self.assertEqual(set(drafts.mapped('state')), {'cancel'})
        self.assertEqual(len(self._rows(order)), 2)

    def test_frequency_revision_metadata_cannot_be_forged_and_is_not_copied(self):
        order = self._order(months=6)
        self._post_first(order)
        order.invoicing_cycle_period = 'per_3_months'
        with self.assertRaises(UserError):
            order.write({'billing_frequency_revision': 0})
        with self.assertRaises(UserError):
            order.with_context(_billing_frequency_token=True).write({'billing_frequency_revision': 0})
        copied = order.copy()
        self.assertFalse(copied.billing_frequency_revision)
        self.assertFalse(copied.billing_engine_line_ids)

    def test_return_date_still_caps_remaining_rental_and_prorates_amount(self):
        order = self._order(months=12)
        order.order_line.bastk_return_date = date(2026, 5, 20)
        self._post_first(order)
        expected = sum(self._rows(order).mapped('amount'))
        order.invoicing_cycle_period = 'per_3_months'
        rows = self._rows(order)
        self.assertEqual(max(rows.mapped('rental_end')), date(2026, 5, 20))
        self.assertEqual(sum(rows.mapped('amount')), expected)
        self.assertEqual(rows[-1].amount, 1600000)

    def test_prorate_keeps_posted_first_partial_and_last_contract_partial(self):
        order = self._order(start=datetime(2026, 1, 14, 5), months=12,
                            delivery=date(2026, 1, 14), billing_rule='prorate')
        posted, retained = self._post_first(order)
        expected = sum(self._rows(order).mapped('amount'))
        before = self._posted_snapshot(posted)
        order.invoicing_cycle_period = 'per_3_months'
        self.assertEqual(self._rows(order)[1].rental_start, date(2026, 2, 1))
        self.assertEqual(self._rows(order)[-1].rental_end, date(2027, 1, 13))
        self.assertEqual(sum(self._rows(order).mapped('amount')), expected)
        self.assertEqual(self._posted_snapshot(posted), before)
        self.assertEqual(self._rows(order)[:1], retained)

    def test_six_month_batch_and_remaining_frequency_groups_continue_to_work(self):
        order = self._order(months=12)
        self._post_first(order)
        order.invoicing_cycle_period = 'per_3_months'
        first = order._generate_billing_engine_invoices(current_month_only=False, batch_months=6)
        self.assertEqual(len(first), 2)
        second = order._generate_billing_engine_invoices(current_month_only=False, batch_months=6)
        self.assertEqual(len(second), 2)
        self.assertFalse(order._generate_billing_engine_invoices(current_month_only=False, batch_months=6))

    def test_all_frequencies_and_short_last_cycle(self):
        for frequency, count in [('monthly', 9), ('per_3_months', 3), ('per_6_months', 2),
                                  ('yearly', 1), ('as_duration', 1)]:
            order = self._order(months=10, invoicing_cycle_period='per_3_months')
            # Start from actual posted monthly coverage, regardless of target label.
            order.invoicing_cycle_period = 'monthly'
            self._post_first(order)
            if frequency == 'monthly':
                order.invoicing_cycle_period = 'per_3_months'
            order.invoicing_cycle_period = frequency
            self.assertEqual(len(self._rows(order).filtered(lambda row: not row.invoice_id)), count)
            self.assertEqual(sum(self._rows(order).mapped('amount')), 30000000)

    def test_noop_save_does_not_cancel_drafts_or_consume_revision(self):
        order = self._order(months=6)
        drafts = self._all_invoices(order)
        order.invoicing_cycle_period = order.invoicing_cycle_period
        self.assertEqual(set(drafts.mapped('state')), {'draft'})
        self.assertFalse(order.billing_frequency_revision)

    def test_structural_fields_and_once_amendments_cannot_piggyback_on_frequency(self):
        order = self._order(months=6)
        drafts = self._all_invoices(order)
        for extra in ({'masa_sewa_bulan': 12}, {'top_billing': 'dibelakang'},
                      {'order_line': [Command.unlink(order.order_line.id)]}):
            with self.assertRaises(UserError):
                order.write({'invoicing_cycle_period': 'per_3_months', **extra})
        self.assertEqual(set(drafts.mapped('state')), {'draft'})
        self.assertEqual(order.invoicing_cycle_period, 'monthly')

    def test_native_view_frequency_is_editable_in_sales_order(self):
        arch = etree.fromstring(self.env['sale.order'].get_view(view_type='form')['arch'])
        nodes = arch.xpath("//field[@name='invoicing_cycle_period']")
        self.assertTrue(nodes)
        self.assertTrue(all("'sale'" not in node.get('readonly', '') for node in nodes))

    def test_exact_unlinked_legacy_posted_invoice_is_adopted_before_rebuild(self):
        order = self._order(months=6)
        posted, row = self._post_first(order)
        before = self._posted_snapshot(posted)
        row.sudo().write({'invoice_id': False, 'invoice_line_id': False})
        order.invoicing_cycle_period = 'per_3_months'
        self.assertEqual(row.invoice_id, posted)
        self.assertEqual(self._posted_snapshot(posted), before)
        self.assertEqual(self._rows(order).mapped('period_start'), [date(2026, m, 1) for m in (1, 2, 5)])

    def test_ambiguous_legacy_invoice_requires_review_without_cancellation(self):
        order = self._order(months=6)
        self._all_invoices(order)
        row = self._rows(order)[:1]
        invoice = row.invoice_id
        row.sudo().write({'invoice_id': False, 'invoice_line_id': False})
        invoice.invoice_line_ids.price_unit += 1
        with self.assertRaisesRegex(UserError, 'does not match'):
            order.invoicing_cycle_period = 'per_3_months'
        self.assertEqual(invoice.state, 'draft')
        self.assertEqual(order.invoicing_cycle_period, 'monthly')

    def test_posted_invoice_with_active_receive_voucher_is_retained(self):
        if 'prv.voucher' not in self.env:
            self.skipTest('Optional voucher addon not installed')
        manager = new_test_user(self.env, login='frequency_voucher_manager',
                                groups='payment_receive_voucher.group_voucher_manager,account.group_account_invoice',
                                company_id=self.company.id, company_ids=[Command.set(self.company.ids)])
        order = self._order(months=6)
        posted, retained = self._post_first(order)
        config = self.env['prv.voucher.config'].create({
            'name': 'Frequency Receive Approval', 'voucher_type': 'receive',
            'company_id': self.company.id,
            'layer_ids': [Command.create({'sequence': 1, 'min_amount': 0, 'approver_id': manager.id})],
        })
        voucher = self.env['prv.voucher'].with_user(manager).create({
            'voucher_type': 'receive', 'move_ids': [Command.set(posted.ids)]})
        voucher.action_submit()
        before = self._posted_snapshot(posted)
        snapshot = voucher.bill_ids.read(['amount', 'original_total', 'move_id'])
        order.invoicing_cycle_period = 'per_3_months'
        self.assertEqual(voucher.state, 'waiting')
        self.assertEqual(voucher.config_id, config)
        self.assertEqual(voucher.bill_ids.read(['amount', 'original_total', 'move_id']), snapshot)
        self.assertEqual(self._posted_snapshot(posted), before)
        self.assertEqual(retained.invoice_id, posted)

    def test_paid_posted_invoice_payment_and_reconciliation_are_not_modified(self):
        order = self._order(months=6)
        posted, retained = self._post_first(order)
        bank_account = self.env['account.account'].create({
            'name': 'Frequency Bank', 'code': '79999401', 'account_type': 'asset_cash',
            'company_ids': [Command.set(self.company.ids)],
        })
        outstanding = self.env['account.account'].create({
            'name': 'Frequency Outstanding', 'code': '79999402', 'account_type': 'asset_current',
            'reconcile': True, 'company_ids': [Command.set(self.company.ids)],
        })
        bank = self.env['account.journal'].create({
            'name': 'Frequency Bank', 'code': 'FREQB', 'type': 'bank',
            'company_id': self.company.id, 'default_account_id': bank_account.id,
        })
        bank.inbound_payment_method_line_ids.payment_account_id = outstanding
        wizard = self.env['account.payment.register'].with_context(
            active_model='account.move', active_ids=posted.ids).create({'journal_id': bank.id})
        payment = wizard._create_payments()
        self.assertEqual(posted.amount_residual, 0)
        before = self._posted_snapshot(posted)
        matches = posted.line_ids.matched_credit_ids | posted.line_ids.matched_debit_ids
        reconciles = matches.read(['amount', 'debit_move_id', 'credit_move_id'])
        payment_before = payment.read(['state', 'amount', 'move_id'])
        order.invoicing_cycle_period = 'per_3_months'
        self.assertEqual(self._posted_snapshot(posted), before)
        self.assertEqual(posted.amount_residual, 0)
        self.assertEqual(matches.read(['amount', 'debit_move_id', 'credit_move_id']), reconciles)
        self.assertEqual(payment.read(['state', 'amount', 'move_id']), payment_before)
        self.assertEqual(retained.invoice_id, posted)
