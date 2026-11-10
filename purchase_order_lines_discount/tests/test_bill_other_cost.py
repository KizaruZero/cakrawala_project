from lxml import etree

from odoo import Command, fields
from odoo.exceptions import UserError, ValidationError
from odoo.tests import Form, tagged
from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged('post_install', '-at_install')
class TestBillOtherCost(AccountTestInvoicingCommon):
    def _tax(self, amount=11, included=False):
        return self.env['account.tax'].create({
            'name': 'Test Purchase %s %s' % (amount, self.env['account.tax'].search_count([])),
            'amount': amount, 'amount_type': 'percent',
            'type_tax_use': 'purchase', 'company_id': self.env.company.id,
            'price_include_override': 'tax_included' if included else 'tax_excluded',
        })

    def _bill(self, taxes=None, kind='in_invoice', currency=None, **values):
        return self.env['account.move'].create({
            'move_type': kind, 'partner_id': self.partner_a.id, 'invoice_date': fields.Date.today(),
            'currency_id': (currency or self.env.company.currency_id).id,
            'invoice_line_ids': [Command.create({
                'name': 'Unit test', 'quantity': 1, 'price_unit': 1000000,
                'account_id': self.company_data['default_account_expense'].id,
                'tax_ids': [Command.set(taxes.ids if taxes else [])], **values,
            })],
        })

    def _assert_amounts(self, bill, subtotal, tax):
        self.assertAlmostEqual(bill.invoice_line_ids.price_subtotal, subtotal, places=2)
        self.assertAlmostEqual(bill.amount_untaxed, subtotal, places=2)
        self.assertAlmostEqual(bill.amount_tax, tax, places=2)
        self.assertAlmostEqual(bill.amount_total, subtotal + tax, places=2)
        self.assertAlmostEqual(bill.amount_residual, subtotal + tax, places=2)
        self.assertAlmostEqual(sum(bill.line_ids.mapped('balance')), 0, places=2)

    def test_once_per_line_after_fixed_discount_and_quantity_changes(self):
        bill = self._bill(self._tax(), quantity=2, fixed_discount_type='fixed',
                          fixed_discount=200000, other_cost_deduction=100000)
        self._assert_amounts(bill, 1700000, 187000)
        bill.invoice_line_ids.quantity = 3
        self._assert_amounts(bill, 2700000, 297000)
        self.assertEqual(bill.invoice_line_ids.fixed_discount, 200000)
        self.assertEqual(bill.invoice_line_ids.other_cost_deduction, 100000)

    def test_amount_only_edit_and_clear_sync_native_tax_and_payable(self):
        bill = self._bill(self._tax(), discount=10)
        line = bill.invoice_line_ids
        for cost, subtotal in [(100000, 800000), (200000, 700000), (0, 900000)]:
            line.other_cost_deduction = cost
            self._assert_amounts(bill, subtotal, subtotal * .11)
            self.assertEqual(line.price_unit, 1000000)
            self.assertEqual(line.discount, 10)
        line.write({'fixed_discount_type': 'fixed', 'fixed_discount': 250000})
        self._assert_amounts(bill, 750000, 82500)

    def test_included_tax_deducts_exactly_from_dpp_not_gross(self):
        bill = self._bill(self._tax(included=True), price_unit=1110000, other_cost_deduction=50000)
        self._assert_amounts(bill, 950000, 104500)
        bill.invoice_line_ids.other_cost_deduction = 100000
        self._assert_amounts(bill, 900000, 99000)
        bill.invoice_line_ids.other_cost_deduction = 0
        self._assert_amounts(bill, 1000000, 110000)

    def test_mixed_ppn_pph_after_deduction(self):
        bill = self._bill(self._tax() | self._tax(-2), other_cost_deduction=100000)
        self._assert_amounts(bill, 900000, 81000)

    def test_posting_and_vendor_credit_note_preserve_reduced_base(self):
        for kind in ('in_invoice', 'in_refund'):
            bill = self._bill(self._tax(), kind=kind, other_cost_deduction=100000)
            bill.action_post()
            self._assert_amounts(bill, 900000, 99000)
            with self.assertRaises(UserError):
                bill.invoice_line_ids.other_cost_deduction = 200000
            bill.invoice_line_ids.other_cost_deduction = 100000
            self._assert_amounts(bill, 900000, 99000)

    def test_invalid_deductions_rejected(self):
        for values in ({'other_cost_deduction': -1}, {'other_cost_deduction': float('inf')},
                       {'other_cost_deduction': 1000001},
                       {'other_cost_deduction': 1, 'quantity': 0},
                       {'other_cost_deduction': 1, 'quantity': -1}):
            with self.assertRaises(ValidationError), self.cr.savepoint():
                self._bill(**values)
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self._bill(kind='out_invoice', other_cost_deduction=1)

    def test_deduction_equal_to_base_can_be_edited_and_removed(self):
        bill = self._bill(self._tax(), other_cost_deduction=1000000)
        self._assert_amounts(bill, 0, 0)
        bill.invoice_line_ids.other_cost_deduction = 0
        self._assert_amounts(bill, 1000000, 110000)

    def test_form_onchange_and_save_show_same_subtotal(self):
        bill = self._bill(self._tax(), discount=10)
        with Form(bill) as form:
            with form.invoice_line_ids.edit(0) as line:
                line.other_cost_deduction = 100000
                self.assertAlmostEqual(line.price_subtotal, 800000, places=2)
        self._assert_amounts(bill, 800000, 88000)

    def test_native_credit_note_copies_deduction_without_changing_original(self):
        bill = self._bill(self._tax(), other_cost_deduction=100000)
        bill.action_post()
        reverse = bill._reverse_moves(default_values_list=[{'date': fields.Date.today()}])
        self.assertEqual(reverse.move_type, 'in_refund')
        self.assertEqual(reverse.invoice_line_ids.other_cost_deduction, 100000)
        self._assert_amounts(reverse, 900000, 99000)
        self._assert_amounts(bill, 900000, 99000)

    def test_foreign_currency_deduction_and_company_journal_balance(self):
        currency = self.env.ref('base.IDR')
        currency.active = True
        self.env['res.currency.rate'].create({'currency_id': currency.id,
            'company_id': self.env.company.id, 'name': fields.Date.today(), 'rate': 15000})
        bill = self._bill(self._tax(), currency=currency, other_cost_deduction=100000)
        self._assert_amounts(bill, 900000, 99000)
        bill.invoice_line_ids.other_cost_deduction = 200000
        self._assert_amounts(bill, 800000, 88000)
        expected = currency._convert(800000, self.env.company.currency_id,
                                     self.env.company, bill.date)
        self.assertAlmostEqual(bill.invoice_line_ids.balance, expected, places=2)
        bill.action_post()
        self._assert_amounts(bill, 800000, 88000)

    def test_batch_lines_and_invalid_edit_are_atomic(self):
        bill = self._bill(self._tax(), other_cost_deduction=100000)
        bill.invoice_line_ids.copy({'move_id': bill.id})
        self.assertAlmostEqual(bill.amount_total, 1998000)
        bill.invoice_line_ids.write({'other_cost_deduction': 200000})
        self.assertAlmostEqual(bill.amount_untaxed, 1600000)
        self.assertAlmostEqual(bill.amount_total, 1776000)
        before = bill.invoice_line_ids.read(['price_unit', 'discount', 'other_cost_deduction', 'price_subtotal'])
        with self.assertRaises(ValidationError), self.cr.savepoint():
            bill.invoice_line_ids.write({'other_cost_deduction': 1000001})
        self.assertEqual(bill.invoice_line_ids.read(['price_unit', 'discount', 'other_cost_deduction', 'price_subtotal']), before)
        self.assertAlmostEqual(bill.amount_total, 1776000)
        bill.invoice_line_ids.write({'other_cost_deduction': 1000000})
        self.assertAlmostEqual(bill.amount_total, 0)

    def test_unset_cost_preserves_legacy_calculation_and_form_column(self):
        bill = self._bill(self._tax(included=True), price_unit=1110000,
                          fixed_discount=111000, fixed_discount_type='fixed')
        self._assert_amounts(bill, 900000, 99000)
        self.assertEqual(bill.invoice_line_ids.other_cost_deduction, 0)
        root = etree.fromstring(self.env['account.move'].get_view(view_type='form')['arch'])
        field = root.xpath("//field[@name='invoice_line_ids']/list/field[@name='other_cost_deduction']")[0]
        self.assertIn('in_invoice', field.get('column_invisible'))
        self.assertIn('draft', field.get('readonly'))
