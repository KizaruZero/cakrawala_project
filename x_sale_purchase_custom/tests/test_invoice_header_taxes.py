from lxml import etree

from odoo import Command
from odoo.exceptions import UserError, ValidationError
from odoo.tests import Form, TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestInvoiceHeaderTaxes(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.company.company_code = 'HTAX'
        cls.company.account_fiscal_country_id = cls.env.ref('base.id')
        cls.tax_group = cls.env['account.tax.group'].create({
            'name': 'Header Tax QA Group', 'company_id': cls.company.id,
            'country_id': cls.env.ref('base.id').id,
        })
        cls.accounts = {}
        for index, (name, kind) in enumerate([('income', 'income'), ('expense', 'expense'),
                                             ('receivable', 'asset_receivable'), ('payable', 'liability_payable')], 1):
            cls.accounts[name] = cls.env['account.account'].create({
                'name': 'Header Tax QA ' + name, 'code': '7999950%s' % index, 'account_type': kind,
                'company_ids': [Command.set(cls.company.ids)], 'reconcile': kind in ('asset_receivable', 'liability_payable'),
            })
        cls.partner = cls.env['res.partner'].create({
            'name': 'Header Tax QA Partner', 'property_account_receivable_id': cls.accounts['receivable'].id,
            'property_account_payable_id': cls.accounts['payable'].id,
        })
        cls.journals = {}
        for direction, kind, account in [('out_invoice', 'sale', 'income'), ('in_invoice', 'purchase', 'expense')]:
            cls.journals[direction] = cls.env['account.journal'].create({
                'name': 'Header Tax QA ' + kind, 'code': 'HTS' if kind == 'sale' else 'HTP',
                'type': kind, 'company_id': cls.company.id, 'default_account_id': cls.accounts[account].id,
            })
        cls.entry_journal = cls.env['account.journal'].create({
            'name': 'Header Tax QA Journal Entry', 'code': 'HTJ',
            'type': 'general', 'company_id': cls.company.id,
        })
        cls.taxes = {}
        for use in ('sale', 'purchase'):
            cls.taxes[use] = cls.env['account.tax'].create([
                {'name': 'Header QA PPN ' + use, 'amount': 11, 'type_tax_use': use, 'company_id': cls.company.id, 'tax_group_id': cls.tax_group.id},
                {'name': 'Header QA PPh ' + use, 'amount': -2, 'type_tax_use': use, 'company_id': cls.company.id, 'tax_group_id': cls.tax_group.id},
            ])
        cls.product = cls.env['product.product'].create({
            'name': 'Header Tax QA Product', 'type': 'service',
            'property_account_income_id': cls.accounts['income'].id,
            'property_account_expense_id': cls.accounts['expense'].id,
            'taxes_id': [Command.set(cls.taxes['sale'][:1].ids)],
            'supplier_taxes_id': [Command.set(cls.taxes['purchase'][:1].ids)],
        })

    def _move(self, direction='out_invoice', **values):
        return self.env['account.move'].create({
            'move_type': direction, 'partner_id': self.partner.id, 'company_id': self.company.id,
            'journal_id': self.journals[direction].id,
            'invoice_line_ids': [Command.create({'product_id': self.product.id, 'name': name,
                                                'quantity': 1, 'price_unit': price, 'tax_ids': [Command.clear()]})
                                 for name, price in [('Vehicle', 1000000), ('Biaya Materai', 10000)]],
            **values,
        })

    def _entry_values(self, **values):
        return {
            'move_type': 'entry', 'journal_id': self.entry_journal.id,
            'company_id': self.company.id,
            'line_ids': [
                Command.create({'name': 'Native taxable journal debit',
                                'account_id': self.accounts['expense'].id, 'debit': 100,
                                'tax_ids': [Command.set(self.taxes['purchase'][:1].ids)]}),
                Command.create({'name': 'Journal credit',
                                'account_id': self.accounts['income'].id, 'credit': 100}),
            ],
            **values,
        }

    def _entry_snapshot(self, move):
        return move.line_ids.read(['name', 'account_id', 'partner_id', 'balance',
                                   'debit', 'credit', 'amount_currency', 'tax_ids',
                                   'analytic_distribution'])

    def test_journal_entry_empty_header_commands_do_not_clear_line_taxes(self):
        for empty in (False, [], [Command.clear()], [Command.set([])],
                      [Command.link(self.taxes['purchase'][0].id),
                       Command.unlink(self.taxes['purchase'][0].id)]):
            with self.subTest(empty=empty):
                move = self.env['account.move'].create(self._entry_values(header_tax_ids=empty))
                self.assertFalse(move.header_tax_ids)
                self.assertEqual(move.line_ids.filtered(lambda line: line.debit).tax_ids,
                                 self.taxes['purchase'][:1])
                before = self._entry_snapshot(move)
                move.write({'header_tax_ids': empty})
                self.assertEqual(self._entry_snapshot(move), before)

    def test_journal_entry_empty_context_default_is_harmless(self):
        move = self.env['account.move'].with_context(default_header_tax_ids=[Command.clear()]).create(
            self._entry_values())
        self.assertFalse(move.header_tax_ids)
        self.assertEqual(move.line_ids.filtered(lambda line: line.debit).tax_ids,
                         self.taxes['purchase'][:1])

    def test_posted_and_cancelled_journal_entry_empty_header_preserves_lines(self):
        move = self.env['account.move'].create(self._entry_values())
        move.action_post()
        before = self._entry_snapshot(move)
        move.write({'header_tax_ids': [Command.clear()]})
        self.assertEqual(move.state, 'posted')
        self.assertEqual(self._entry_snapshot(move), before)
        move.button_draft()
        move.button_cancel()
        before = self._entry_snapshot(move)
        move.write({'header_tax_ids': [Command.set([])]})
        self.assertEqual(move.state, 'cancel')
        self.assertEqual(self._entry_snapshot(move), before)

    def test_real_header_tax_on_journal_entry_still_rejected(self):
        selected = [Command.set(self.taxes['purchase'].ids)]
        with self.assertRaisesRegex(ValidationError, 'only available on Customer Invoices'), self.env.cr.savepoint():
            self.env['account.move'].create(self._entry_values(header_tax_ids=selected))
        move = self.env['account.move'].create(self._entry_values())
        before = self._entry_snapshot(move)
        with self.assertRaisesRegex(ValidationError, 'only available on Customer Invoices'), self.env.cr.savepoint():
            move.write({'header_tax_ids': selected})
        self.assertFalse(move.header_tax_ids)
        self.assertEqual(self._entry_snapshot(move), before)
        with self.assertRaisesRegex(ValidationError, 'only available on Customer Invoices'), self.env.cr.savepoint():
            self.env['account.move'].with_context(default_header_tax_ids=selected).create(
                self._entry_values())

    def test_mixed_recordset_clears_invoice_header_only(self):
        entry = self.env['account.move'].create(self._entry_values())
        entry.action_post()
        invoice = self._move(header_tax_ids=[Command.set(self.taxes['sale'].ids)])
        bill = self._move('in_invoice', header_tax_ids=[Command.set(self.taxes['purchase'].ids)])
        before = self._entry_snapshot(entry)
        (entry | invoice | bill).write({'header_tax_ids': [Command.clear()]})
        self.assertEqual(self._entry_snapshot(entry), before)
        self.assertFalse((invoice | bill).invoice_line_ids.tax_ids)

    def test_mixed_posted_invoice_still_blocks_header_write_atomically(self):
        entry = self.env['account.move'].create(self._entry_values())
        invoice = self._move(header_tax_ids=[Command.set(self.taxes['sale'].ids)])
        invoice.action_post()
        before = self._entry_snapshot(entry | invoice)
        with self.assertRaisesRegex(UserError, 'only be changed on Draft'):
            (entry | invoice).write({'header_tax_ids': [Command.clear()]})
        self.assertEqual(self._entry_snapshot(entry | invoice), before)
        self.assertEqual(invoice.header_tax_ids, self.taxes['sale'])

    def test_mixed_multi_create_checks_each_document_type(self):
        def invoice_values(direction, use):
            return {
                'move_type': direction, 'partner_id': self.partner.id,
                'journal_id': self.journals[direction].id,
                'header_tax_ids': [Command.set(self.taxes[use].ids)],
                'invoice_line_ids': [Command.create({'product_id': self.product.id,
                                                   'quantity': 1, 'price_unit': 100})],
            }
        entry, invoice, bill = self.env['account.move'].create([
            self._entry_values(header_tax_ids=[Command.clear()]),
            invoice_values('out_invoice', 'sale'), invoice_values('in_invoice', 'purchase'),
        ])
        self.assertFalse(entry.header_tax_ids)
        self.assertEqual(entry.line_ids.filtered(lambda line: line.debit).tax_ids,
                         self.taxes['purchase'][:1])
        self.assertEqual(invoice.invoice_line_ids.tax_ids, self.taxes['sale'])
        self.assertEqual(bill.invoice_line_ids.tax_ids, self.taxes['purchase'])
        self.assertAlmostEqual(invoice.amount_total, 109)
        self.assertAlmostEqual(bill.amount_total, 109)

    def test_refunds_and_receipts_ignore_only_empty_header(self):
        for direction in ('out_refund', 'in_refund', 'out_receipt', 'in_receipt'):
            use = 'sale' if direction.startswith('out_') else 'purchase'
            journal = self.journals['out_invoice' if use == 'sale' else 'in_invoice']
            values = {
                'move_type': direction, 'partner_id': self.partner.id,
                'journal_id': journal.id, 'header_tax_ids': [Command.clear()],
                'invoice_line_ids': [Command.create({'product_id': self.product.id,
                                                   'quantity': 1, 'price_unit': 100,
                                                   'tax_ids': [Command.set(self.taxes[use].ids)]})],
            }
            with self.subTest(move_type=direction):
                move = self.env['account.move'].create(values)
                self.assertEqual(move.invoice_line_ids.tax_ids, self.taxes[use])
                before = self._entry_snapshot(move)
                move.write({'header_tax_ids': [Command.set([])]})
                self.assertEqual(self._entry_snapshot(move), before)
                with self.assertRaisesRegex(ValidationError, 'only available on Customer Invoices'), self.env.cr.savepoint():
                    move.write({'header_tax_ids': [Command.set(self.taxes[use].ids)]})

    def test_journal_copy_and_reversal_keep_native_line_taxes(self):
        entry = self.env['account.move'].create(self._entry_values(header_tax_ids=[Command.clear()]))
        copied = entry.copy()
        self.assertFalse(copied.header_tax_ids)
        self.assertEqual(copied.line_ids.filtered(lambda line: line.debit).tax_ids,
                         self.taxes['purchase'][:1])
        entry.action_post()
        reversed_move = entry._reverse_moves(cancel=False)
        self.assertFalse(reversed_move.header_tax_ids)
        self.assertEqual(reversed_move.line_ids.filtered(lambda line: line.credit).tax_ids,
                         self.taxes['purchase'][:1])

    def test_wrong_tax_direction_on_write_still_rejected(self):
        for direction, wrong in [('out_invoice', 'purchase'), ('in_invoice', 'sale')]:
            move = self._move(direction)
            with self.assertRaisesRegex(ValidationError, 'Select Sales taxes'), self.env.cr.savepoint():
                move.write({'header_tax_ids': [Command.set(self.taxes[wrong].ids)]})
            self.assertFalse(move.header_tax_ids)

    def test_manual_journal_form_saves_and_posts(self):
        with Form(self.env['account.move'].with_context(default_move_type='entry',
                                                       default_journal_id=self.entry_journal.id)) as form:
            with form.line_ids.new() as debit:
                debit.account_id = self.accounts['expense']
                debit.name = 'Manual entry debit'
                debit.debit = 100
            with form.line_ids.new() as credit:
                credit.account_id = self.accounts['income']
                credit.name = 'Manual entry credit'
                credit.credit = 100
        entry = form.record
        entry.write({'header_tax_ids': [Command.clear()]})
        entry.action_post()
        self.assertEqual(entry.state, 'posted')
        self.assertFalse(entry.header_tax_ids)
        self.assertAlmostEqual(sum(entry.line_ids.mapped('balance')), 0)

    def test_header_tax_on_create_applies_multiple_taxes_for_both_documents(self):
        for direction, use in [('out_invoice', 'sale'), ('in_invoice', 'purchase')]:
            taxes = self.taxes[use]
            move = self._move(direction, header_tax_ids=[Command.set(taxes.ids)])
            self.assertTrue(all(line.tax_ids == taxes for line in move.invoice_line_ids))
            self.assertAlmostEqual(move.amount_untaxed, 1010000)
            self.assertAlmostEqual(move.amount_total, 1100900)

    def test_existing_taxes_are_replaced_and_clearing_header_clears_item_taxes(self):
        move = self._move()
        move.invoice_line_ids.tax_ids = self.taxes['sale'][:1]
        before = move.invoice_line_ids.read(['name', 'quantity', 'price_unit', 'account_id'])
        move.header_tax_ids = self.taxes['sale'][1:]
        self.assertTrue(all(line.tax_ids == self.taxes['sale'][1:] for line in move.invoice_line_ids))
        move.header_tax_ids = self.taxes['sale']
        self.assertTrue(all(line.tax_ids == self.taxes['sale'] for line in move.invoice_line_ids))
        move.header_tax_ids = [Command.clear()]
        self.assertFalse(move.invoice_line_ids.tax_ids)
        self.assertEqual(move.invoice_line_ids.read(['name', 'quantity', 'price_unit', 'account_id']), before)

    def test_without_header_native_product_and_explicit_line_taxes_are_unchanged(self):
        move = self._move()
        self.assertFalse(move.header_tax_ids)
        self.assertFalse(move.invoice_line_ids.tax_ids)
        line = self.env['account.move.line'].create({'move_id': move.id, 'product_id': self.product.id, 'price_unit': 200})
        self.assertEqual(line.tax_ids, self.taxes['sale'][:1])

    def test_new_lines_and_product_change_use_header_but_manual_line_override_is_allowed(self):
        move = self._move(header_tax_ids=[Command.set(self.taxes['sale'].ids)])
        line = self.env['account.move.line'].create({'move_id': move.id, 'product_id': self.product.id, 'price_unit': 200})
        self.assertEqual(line.tax_ids, move.header_tax_ids)
        line.tax_ids = self.taxes['sale'][:1]
        self.assertEqual(line.tax_ids, self.taxes['sale'][:1])
        line.price_unit = 300
        self.assertEqual(line.tax_ids, self.taxes['sale'][:1])
        other = self.product.copy({'name': 'Another Header Tax QA Product'})
        line.product_id = other
        # Native Odoo preserves a manual override when the replacement product
        # has the same defaults. The header is a bulk/default input, not a lock.
        self.assertEqual(line.tax_ids, self.taxes['sale'][:1])

    def test_sections_notes_and_tax_payment_journal_lines_are_not_direct_targets(self):
        move = self._move(invoice_line_ids=[
            Command.create({'display_type': 'line_section', 'name': 'Header QA Section'}),
            Command.create({'product_id': self.product.id, 'price_unit': 1000000, 'tax_ids': [Command.clear()]}),
            Command.create({'display_type': 'line_note', 'name': 'Header QA Note'}),
        ])
        move.header_tax_ids = self.taxes['sale']
        excluded = move.line_ids.filtered(lambda line: line.display_type in ('line_section', 'line_note', 'payment_term'))
        self.assertFalse(excluded.tax_ids)
        self.assertEqual(move.invoice_line_ids.filtered(lambda line: line.display_type == 'product').tax_ids, self.taxes['sale'])

    def test_posted_and_cancelled_moves_reject_header_changes(self):
        move = self._move(header_tax_ids=[Command.set(self.taxes['sale'].ids)])
        move.action_post()
        before = move.line_ids.read(['balance', 'tax_ids', 'name'])
        with self.assertRaisesRegex(UserError, 'only be changed on Draft'):
            move.header_tax_ids = [Command.clear()]
        self.assertEqual(move.line_ids.read(['balance', 'tax_ids', 'name']), before)
        move.button_draft()
        move.button_cancel()
        with self.assertRaises(UserError):
            move.header_tax_ids = self.taxes['sale']

    def test_wrong_tax_direction_is_rejected(self):
        for direction, use in [('out_invoice', 'purchase'), ('in_invoice', 'sale')]:
            with self.assertRaisesRegex(ValidationError, 'Select Sales taxes'):
                self._move(direction, header_tax_ids=[Command.set(self.taxes[use].ids)])

    def test_other_company_taxes_are_rejected(self):
        other = self.env['res.company'].create({'name': 'Header Tax QA Other', 'company_code': 'HTX2', 'country_id': self.env.ref('base.id').id})
        group = self.env['account.tax.group'].create({'name': 'Other Header Tax QA Group', 'company_id': other.id, 'country_id': self.env.ref('base.id').id})
        tax = self.env['account.tax'].create({'name': 'Foreign Header QA', 'amount': 11, 'type_tax_use': 'sale', 'company_id': other.id, 'tax_group_id': group.id})
        with self.assertRaises(UserError):
            self._move(header_tax_ids=[Command.set(tax.ids)])

    def test_native_fiscal_mapping_is_not_applied_twice_to_manually_selected_taxes(self):
        destination = self.taxes['sale'][1:].copy({
            'name': 'Header QA Fiscal Destination', 'original_tax_ids': [Command.set(self.taxes['sale'][:1].ids)],
        })
        fiscal = self.env['account.fiscal.position'].create({
            'name': 'Header Tax QA Fiscal', 'company_id': self.company.id,
            'tax_ids': [Command.set(destination.ids)],
        })
        self.assertEqual(fiscal.map_tax(self.taxes['sale'][:1]), destination)
        move = self._move(fiscal_position_id=fiscal.id, header_tax_ids=[Command.set(self.taxes['sale'][:1].ids)])
        self.assertTrue(all(line.tax_ids == self.taxes['sale'][:1] for line in move.invoice_line_ids))

    def test_form_onchange_applies_header_and_new_product_line(self):
        move = self._move()
        with Form(move) as form:
            form.header_tax_ids.add(self.taxes['sale'][:1])
            form.header_tax_ids.add(self.taxes['sale'][1:])
            with form.invoice_line_ids.new() as line:
                line.product_id = self.product
                line.price_unit = 1000000
        self.assertTrue(all(line.tax_ids == move.header_tax_ids for line in move.invoice_line_ids))

    def test_header_is_not_copied_and_historic_invoice_line_taxes_stay_copied(self):
        move = self._move(header_tax_ids=[Command.set(self.taxes['sale'].ids)])
        copied = move.copy()
        self.assertFalse(copied.header_tax_ids)
        self.assertTrue(all(line.tax_ids == self.taxes['sale'] for line in copied.invoice_line_ids))

    def test_view_has_many2many_header_in_draft_only(self):
        root = etree.fromstring(self.env.ref('x_sale_purchase_custom.view_move_form_inherit_rental_invoice').arch_db)
        field = root.xpath('//field[@name="header_tax_ids"]')[0]
        self.assertEqual(field.get('widget'), 'many2many_tags')
        self.assertEqual(field.get('readonly'), "state != 'draft'")

    def test_included_tax_and_fixed_discount_still_use_native_calculation(self):
        included = self.taxes['sale'][:1].copy({'name': 'Included Header QA', 'price_include_override': 'tax_included'})
        move = self._move(header_tax_ids=[Command.set(included.ids)], invoice_line_ids=[
            Command.create({'product_id': self.product.id, 'quantity': 1, 'price_unit': 1110000}),
        ])
        self.assertAlmostEqual(move.amount_untaxed, 1000000)
        self.assertAlmostEqual(move.amount_total, 1110000)
        # The existing fixed-discount addon intentionally applies its absolute
        # discount mode to vendor documents, not Customer Invoices.
        discounted = self._move('in_invoice', header_tax_ids=[Command.set(self.taxes['purchase'].ids)])
        discounted.invoice_line_ids[:1].write({'fixed_discount': 100000, 'fixed_discount_type': 'fixed'})
        self.assertAlmostEqual(discounted.amount_untaxed, 910000)
        self.assertAlmostEqual(discounted.amount_total, 991900)
