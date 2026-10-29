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

