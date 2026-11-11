from odoo.tests import tagged

from .test_bulk_validate import DeferredLifecycleCommon


@tagged('post_install', '-at_install')
class TestDeferredRevenueAnalytic(DeferredLifecycleCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        plan = cls.env['account.analytic.plan'].create({'name': 'Deferred Revenue Unit QA'})
        cls.units = cls.env['account.analytic.account'].create([
            {'name': name, 'plan_id': plan.id, 'company_id': cls.company.id}
            for name in ('B 2411 ZZH', 'B 2054 ZZH')
        ])
        cls.distribution = {str(cls.units[0].id): 60, str(cls.units[1].id): 40}

    def _assert_both_sides(self, entry, moves):
        for move in moves:
            self.assertEqual(len(move.line_ids), 2)
            self.assertEqual(move.line_ids.filtered('debit').analytic_distribution, entry.analytic_distribution)
            self.assertEqual(move.line_ids.filtered('credit').analytic_distribution, entry.analytic_distribution)
            self.assertEqual(sum(move.line_ids.mapped('debit')), sum(move.line_ids.mapped('credit')))

    def test_prepared_revenue_values_copy_distribution_without_changing_accounts_or_amount(self):
        entry = self._entry(analytic_distribution=self.distribution)
        values = entry._prepare_recognition_move_vals(11950000, entry.date, 'Recognition QA')
        debit, credit = [command[2] for command in values['line_ids']]
        self.assertEqual(debit['analytic_distribution'], self.distribution)
        self.assertEqual(credit['analytic_distribution'], self.distribution)
        self.assertEqual((debit['account_id'], debit['debit'], debit['credit']),
                         (self.accounts['liability'].id, 11950000, 0))
        self.assertEqual((credit['account_id'], credit['debit'], credit['credit']),
                         (self.accounts['revenue'].id, 0, 11950000))
        self.assertEqual(entry.analytic_distribution, self.distribution)

    def test_validate_posts_current_periods_and_schedules_future_with_both_analytics(self):
        entry = self._entry(analytic_distribution=self.distribution)
        entry.action_validate()
        moves = entry.line_ids.move_id
        self.assertEqual(len(moves), 3)
        self.assertEqual(set(moves.mapped('state')), {'draft', 'posted'})
        self._assert_both_sides(entry, moves)
        self.assertEqual(entry.original_value, 12000)
        self.assertEqual(entry.recognized_value, 8000)
        self.assertEqual(entry.residual_value, 4000)

    def test_native_analytic_entries_have_opposite_signs_by_general_account(self):
        entry = self._entry(analytic_distribution=self.distribution)
        entry.action_validate()
        posted = entry.line_ids.move_id.filtered(lambda move: move.state == 'posted')
        analytics = posted.line_ids.analytic_line_ids
        recognized = sum(posted.line_ids.mapped('debit'))
        debit_analytics = analytics.filtered(lambda line: line.general_account_id == self.accounts['liability'])
        credit_analytics = analytics.filtered(lambda line: line.general_account_id == self.accounts['revenue'])
        self.assertEqual(sum(debit_analytics.mapped('amount')), -recognized)
        self.assertEqual(sum(credit_analytics.mapped('amount')), recognized)
        self.assertEqual(sum(analytics.mapped('amount')), 0)

    def test_empty_distribution_stays_empty_on_both_sides(self):
        entry = self._entry(analytic_distribution=False)
        entry.action_validate()
        self.assertTrue(all(not line.analytic_distribution for line in entry.line_ids.move_id.line_ids))
        self.assertFalse(entry.line_ids.move_id.line_ids.analytic_line_ids)

    def test_combined_multi_plan_keys_and_percentages_are_copied_exactly(self):
        plan = self.env['account.analytic.plan'].create({'name': 'Deferred Revenue Department QA'})
        department = self.env['account.analytic.account'].create({
            'name': 'Rental Department QA', 'plan_id': plan.id, 'company_id': self.company.id,
        })
        distribution = {f'{self.units[0].id},{department.id}': 50.5,
                        f'{self.units[1].id},{department.id}': 49.5}
        entry = self._entry(analytic_distribution=distribution)
        entry.action_validate()
        self._assert_both_sides(entry, entry.line_ids.move_id)
        self.assertEqual(entry.analytic_distribution, distribution)

    def test_expense_keeps_existing_debit_only_analytic(self):
        entry = self._entry('expense', analytic_distribution=self.distribution)
        entry.action_validate()
        for move in entry.line_ids.move_id:
            debit = move.line_ids.filtered('debit')
            credit = move.line_ids.filtered('credit')
            self.assertEqual(debit.account_id, self.accounts['expense'])
            self.assertEqual(debit.analytic_distribution, self.distribution)
            self.assertEqual(credit.account_id, self.accounts['asset'])
            self.assertFalse(credit.analytic_distribution)

    def test_write_off_new_move_has_both_sides_without_rewriting_posted_moves(self):
        entry = self._entry(analytic_distribution=self.distribution)
        entry.action_validate()
        posted = entry.line_ids.move_id.filtered(lambda move: move.state == 'posted')
        before = posted.line_ids.read(['account_id', 'debit', 'credit', 'analytic_distribution', 'write_date'])
        remaining = entry.line_ids.filtered(lambda line: line.state != 'posted')
        residual = entry.residual_value
        entry.action_write_off_deferred()
        final = remaining.move_id
        self.assertEqual(len(final), 1)
        self.assertEqual(final.state, 'posted')
        self._assert_both_sides(entry, final)
        self.assertEqual(sum(final.line_ids.mapped('credit')), residual)
        self.assertEqual(posted.line_ids.read(list(before[0])), before)
        self.assertEqual(entry.residual_value, 0)

    def test_existing_legacy_moves_are_not_retroactively_changed_or_duplicated(self):
        entry = self._entry(analytic_distribution=self.distribution)
        entry.action_compute_board()
        entry._generate_moves()
        moves = entry.line_ids.move_id
        # Simulate journals materialised by 19.0.1.0.11 before any posting.
        moves.line_ids.filtered('credit').analytic_distribution = False
        entry.action_validate()
        before = moves.line_ids.read(['account_id', 'debit', 'credit', 'analytic_distribution', 'write_date'])
        entry._generate_moves()
        entry.line_ids._ensure_move()
        self.assertEqual(entry.line_ids.move_id, moves)
        self.assertEqual(moves.line_ids.read(list(before[0])), before)
        self.assertTrue(all(not line.analytic_distribution for line in moves.line_ids.filtered('credit')))
