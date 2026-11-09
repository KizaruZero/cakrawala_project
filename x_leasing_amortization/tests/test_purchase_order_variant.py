from odoo import Command
from odoo.exceptions import ValidationError
from odoo.tests import tagged

from .test_early_settlement import LeasingScheduleCommon


@tagged('post_install', '-at_install')
class TestPurchaseOrderLeasingVariant(LeasingScheduleCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.po_type = cls.env['purchase.order.type.master'].create({
            'name': 'Leasing Variant Test Type', 'state': 'active',
            'is_leasing': True, 'company_id': cls.company.id,
        })
        cls.product = cls.env['product.product'].create({
            'name': 'TOYOTA INNOVA ZENIX', 'type': 'consu',
            'purchase_ok': True, 'supplier_taxes_id': [Command.clear()],
        })

    def _po(self, quantities=(1,), descriptions=None):
        descriptions = descriptions or [
            'TOYOTA INNOVA ZENIX\n(Q 2.0 HEV MODELISTA CVT, 2023)',
            'TOYOTA INNOVA ZENIX\n(V 2.0 CVT, 2026)',
        ]
        return self.env['purchase.order'].create({
            'partner_id': self.vendor.id, 'leasing_partner_id': self.vendor.id,
            'purchase_order_type_master_id': self.po_type.id,
            'company_id': self.company.id, 'state': 'purchase',
            'order_line': [Command.create({
                'product_id': self.product.id, 'product_qty': quantity,
                'name': descriptions[index], 'price_unit': 450000000,
                'tax_ids': [Command.clear()],
            }) for index, quantity in enumerate(quantities)],
        })

    def test_single_unit_copies_order_line_description_before_receipt(self):
        po = self._po()
        before = po.order_line.read(['name', 'product_qty', 'price_unit', 'price_subtotal'])
        action = po.action_create_leasing_schedule()
        loan = po.leasing_loan_ids
        self.assertEqual(len(loan), 1)
        self.assertEqual(action['res_id'], loan.id)
        self.assertEqual(loan.purchase_line_id, po.order_line)
        self.assertEqual(loan.vehicle_variant, po.order_line.name)
        self.assertFalse(loan.vehicle_id)
        self.assertEqual(loan.state, 'draft')
        self.assertEqual(po.order_line.read(list(before[0])), before)

    def test_quantity_three_creates_three_documents_with_same_source_description(self):
        po = self._po(quantities=(3,))
        po.action_create_leasing_schedule()
        self.assertEqual(len(po.leasing_loan_ids), 3)
        self.assertEqual(po.leasing_loan_ids.purchase_line_id, po.order_line)
        self.assertEqual(po.leasing_loan_ids.mapped('vehicle_variant'), [po.order_line.name] * 3)
        self.assertEqual(len(set(po.leasing_loan_ids.mapped('name'))), 3)
        with self.assertRaises(ValidationError):
            po.action_create_leasing_schedule()
        self.assertEqual(len(po.leasing_loan_ids), 3)

    def test_two_one_unit_lines_keep_each_description_even_for_same_product(self):
        po = self._po(quantities=(1, 1))
        po.action_create_leasing_schedule()
        self.assertEqual(len(po.leasing_loan_ids), 2)
        for line in po.order_line:
            loan = po.leasing_loan_ids.filtered(lambda record: record.purchase_line_id == line)
            self.assertEqual(len(loan), 1)
            self.assertEqual(loan.vehicle_variant, line.name)

    def test_snapshot_and_manual_variant_are_not_overwritten_when_adding_remaining_units(self):
        po = self._po(quantities=(1,))
        po.action_create_leasing_schedule()
        first = po.leasing_loan_ids
        first.vehicle_variant = 'USER REVIEWED VARIANT'
        po.order_line.write({'product_qty': 2, 'name': 'UPDATED PO DESCRIPTION'})
        po.action_create_leasing_schedule()
        self.assertEqual(first.vehicle_variant, 'USER REVIEWED VARIANT')
        second = po.leasing_loan_ids - first
        self.assertEqual(len(second), 1)
        self.assertEqual(second.vehicle_variant, 'UPDATED PO DESCRIPTION')

    def test_empty_description_falls_back_to_product_display_name(self):
        po = self._po(descriptions=[''])
        po.action_create_leasing_schedule()
        self.assertEqual(po.leasing_loan_ids.vehicle_variant, self.product.display_name)

    def test_other_descriptions_do_not_change_the_existing_variant_snapshot(self):
        po = self._po()
        po.action_create_leasing_schedule()
        before = po.leasing_loan_ids.vehicle_variant
        po.order_line.name = 'ANOTHER DESCRIPTION'
        self.assertEqual(po.leasing_loan_ids.vehicle_variant, before)

    def test_two_generated_unit_lines_use_net_amount_and_distinct_partner_mapping(self):
        po = self._po(quantities=(1, 1))
        leasing = self.env['res.partner'].create({'name': 'ASTRA CREDIT COMPANIES QA', 'is_company': True})
        po.leasing_partner_id = leasing
        po.order_line.write({'price_unit': 631900000, 'fixed_discount': 20000000})
        before = po.order_line.read(['name', 'price_unit', 'fixed_discount', 'price_subtotal', 'product_qty'])
        po.action_create_leasing_schedule()
        self.assertEqual(len(po.leasing_loan_ids), 2)
        self.assertEqual(po.leasing_loan_ids.mapped('harga_otr'), [611900000, 611900000])
        for loan in po.leasing_loan_ids:
            self.assertEqual(loan.total_hutang, loan.harga_otr - loan.down_payment_leasing)
            self.assertEqual(loan.amount_borrowed, loan.total_hutang)
        self.assertEqual(po.leasing_loan_ids.bank_id, leasing)
        self.assertEqual(po.leasing_loan_ids.vendor_id, po.partner_id)
        self.assertNotEqual(po.leasing_loan_ids.vendor_id, leasing)
        self.assertEqual(po.order_line.read(['name', 'price_unit', 'fixed_discount', 'price_subtotal', 'product_qty']), before)

    def test_multi_quantity_line_discount_is_allocated_not_duplicated(self):
        po = self._po(quantities=(2,))
        po.order_line.write({'price_unit': 631900000, 'fixed_discount': 40000000})
        po.action_create_leasing_schedule()
        self.assertEqual(len(po.leasing_loan_ids), 2)
        self.assertEqual(po.leasing_loan_ids.mapped('harga_otr'), [611900000, 611900000])
        self.assertEqual(sum(po.leasing_loan_ids.mapped('harga_otr')), po.order_line.price_subtotal)

    def test_different_source_prices_are_not_averaged_between_products(self):
        po = self._po(quantities=(1, 1))
        po.order_line[0].write({'price_unit': 631900000, 'fixed_discount': 20000000})
        po.order_line[1].write({'price_unit': 500000000, 'fixed_discount': 10000000})
        po.action_create_leasing_schedule()
        for line in po.order_line:
            loan = po.leasing_loan_ids.filtered(lambda loan: loan.purchase_line_id == line)
            self.assertEqual(loan.harga_otr, line.price_subtotal)

    def test_more_units_does_not_rewrite_existing_manual_financial_or_partner_values(self):
        po = self._po(quantities=(1,))
        po.action_create_leasing_schedule()
        first = po.leasing_loan_ids
        first.write({'harga_otr': 111000000, 'vendor_id': self.vendor.id, 'bank_id': False})
        before = first.read(['name', 'harga_otr', 'vendor_id', 'bank_id', 'total_hutang', 'down_payment_leasing'])
        po.order_line.product_qty = 2
        po.leasing_partner_id = self.env['res.partner'].create({'name': 'New Leasing Partner QA', 'is_company': True})
        po.action_create_leasing_schedule()
        self.assertEqual(first.read(['name', 'harga_otr', 'vendor_id', 'bank_id', 'total_hutang', 'down_payment_leasing']), before)
        self.assertEqual((po.leasing_loan_ids - first).bank_id, po.leasing_partner_id)

    def test_fractional_vehicle_quantity_is_rejected_before_creating_any_document(self):
        po = self._po(quantities=(1, 1.5))
        with self.assertRaisesRegex(ValidationError, 'unit utuh'):
            po.action_create_leasing_schedule()
        self.assertFalse(po.leasing_loan_ids)

    def test_no_leasing_partner_still_uses_po_vendor_and_bank_stays_empty(self):
        po = self._po()
        po.leasing_partner_id = False
        po.action_create_leasing_schedule()
        self.assertEqual(po.leasing_loan_ids.vendor_id, po.partner_id)
        self.assertFalse(po.leasing_loan_ids.bank_id)

    def test_label_change_keeps_the_arrears_technical_value(self):
        loan = self.env['account.loan']
        self.assertEqual(loan._fields['bank_id'].string, 'Leasing Partner')
        self.assertEqual(dict(loan._fields['advarr'].selection)['in_arrears'], 'In Arrear / ADDB')
        wizard = self.env['account.loan.compute.wizard']
        self.assertEqual(dict(wizard._fields['flat_advarr'].selection)['in_arrears'], 'In Arrear / ADDB')
        self.assertEqual(dict(wizard._fields['conversion_advarr'].selection)['in_arrears'], 'In Arrear / ADDB')

    def test_net_otr_removes_included_ppn_without_subtracting_discount_twice(self):
        po = self._po()
        tax = self.env['account.tax'].create({
            'name': 'Leasing OTR Included PPN QA', 'amount': 11, 'type_tax_use': 'purchase',
            'company_id': self.company.id, 'tax_group_id': self.tax_group.id,
            'price_include_override': 'tax_included',
        })
        po.order_line.write({'price_unit': 701409000, 'fixed_discount': 22200000, 'tax_ids': [Command.set(tax.ids)]})
        po.action_create_leasing_schedule()
        self.assertEqual(po.leasing_loan_ids.harga_otr, 611900000)

    def test_percent_discount_and_manual_partner_overrides_on_direct_creation(self):
        po = self._po()
        po.order_line.write({'price_unit': 100000000, 'discount': 10, 'fixed_discount': 0})
        po.action_create_leasing_schedule()
        self.assertEqual(po.leasing_loan_ids.harga_otr, 90000000)
        manual = self.env['res.partner'].create({'name': 'Manual Leasing Partner QA', 'is_company': True})
        loan = self.env['account.loan'].create({
            'purchase_order_id': po.id, 'purchase_line_id': po.order_line.id,
            'company_id': self.company.id, 'bank_id': manual.id, 'vendor_id': manual.id,
        })
        self.assertEqual(loan.bank_id, manual)
        self.assertEqual(loan.vendor_id, manual)

