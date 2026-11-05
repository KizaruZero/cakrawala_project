from odoo import Command
from odoo.tests import tagged

from .test_early_settlement import LeasingScheduleCommon


@tagged('post_install', '-at_install')
class TestLeasingVehicleReceipt(LeasingScheduleCommon):
    """The leasing Vehicle follows the GR of its PO line, and its returns."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.po_type = cls.env['purchase.order.type.master'].create({
            'name': 'Leasing Receipt Test Type', 'state': 'active',
            'is_leasing': True, 'company_id': cls.company.id,
        })
        cls.byd = cls._vehicle_product('BYD SEAL')
        cls.honda = cls._vehicle_product('HONDA HR-V')
        cls.brand = cls.env['fleet.vehicle.model.brand'].create({'name': 'ET Brand'})
        cls.model = cls.env['fleet.vehicle.model'].create({'name': 'ET Model', 'brand_id': cls.brand.id})
        cls.warehouse = cls.env['stock.warehouse'].search([('company_id', '=', cls.company.id)], limit=1)
        cls.supplier_location = cls.env.ref('stock.stock_location_suppliers')
        cls.stock_location = cls.warehouse.lot_stock_id

    @classmethod
    def _vehicle_product(cls, name):
        return cls.env['product.product'].create({
            'name': name, 'type': 'consu', 'is_storable': True, 'tracking': 'serial', 'is_vehicle': True,
            'purchase_ok': True, 'supplier_taxes_id': [Command.clear()],
        })

    def _po(self, lines):
        po = self.env['purchase.order'].create({
            'partner_id': self.vendor.id, 'leasing_partner_id': self.vendor.id,
            'purchase_order_type_master_id': self.po_type.id,
            'company_id': self.company.id, 'state': 'purchase',
            'order_line': [Command.create({
                'product_id': product.id, 'product_qty': qty,
                'name': product.name, 'price_unit': 450000000,
                'tax_ids': [Command.clear()],
            }) for product, qty in lines],
        })
        po.action_create_leasing_schedule()
        return po

    def _units(self, product, count):
        vehicles = self.env['fleet.vehicle']
        for _i in range(count):
            lot = self.env['stock.lot'].create({'product_id': product.id, 'company_id': self.company.id})
            vehicles |= self.env['fleet.vehicle'].create({
                'model_id': self.model.id, 'lot_id': lot.id, 'company_id': self.company.id,
            })
        return vehicles

    def _move(self, line, vehicles, returned=None):
        """A move of ``vehicles`` for ``line``: a receipt, or a return of ``returned``."""
        source, dest = self.supplier_location, self.stock_location
        picking_type = self.warehouse.in_type_id
        if returned:
            source, dest = dest, source
            picking_type = self.warehouse.out_type_id
        picking = self.env['stock.picking'].create({
            'picking_type_id': picking_type.id, 'partner_id': self.vendor.id,
            'location_id': source.id, 'location_dest_id': dest.id,
        })
        return self.env['stock.move'].create({
            'product_id': line.product_id.id, 'product_uom_qty': len(vehicles),
            'location_id': source.id, 'location_dest_id': dest.id,
            'picking_id': picking.id, 'picking_type_id': picking_type.id,
            'purchase_line_id': line.id, 'origin_returned_move_id': returned and returned.id,
            'move_line_ids': [Command.create({
                'product_id': line.product_id.id, 'lot_id': vehicle.lot_id.id, 'quantity': 1,
                'location_id': source.id, 'location_dest_id': dest.id,
            }) for vehicle in vehicles],
        })

    def _loans(self, po, product):
        return po.leasing_loan_ids.filtered(lambda loan: loan.purchase_line_id.product_id == product).sorted('id')

    def test_receipt_fills_only_the_schedules_of_its_variant_in_order(self):
        po = self._po([(self.byd, 3), (self.honda, 2)])
        self.assertEqual(len(po.leasing_loan_ids), 5)
        self.assertFalse(po.leasing_loan_ids.vehicle_id)
        honda_line = po.order_line.filtered(lambda line: line.product_id == self.honda)

        honda = self._units(self.honda, 1)
        self._move(honda_line, honda)._sync_leasing_vehicles()

        honda_loans = self._loans(po, self.honda)
        self.assertEqual(honda_loans[0].vehicle_id, honda)
        self.assertFalse(honda_loans[1].vehicle_id)
        self.assertFalse(self._loans(po, self.byd).vehicle_id)

    def test_partial_receipts_fill_the_next_empty_schedule(self):
        po = self._po([(self.byd, 3)])
        first, second = self._units(self.byd, 1), self._units(self.byd, 2)
        self._move(po.order_line, first)._sync_leasing_vehicles()
        self._move(po.order_line, second)._sync_leasing_vehicles()
        self.assertEqual(self._loans(po, self.byd).vehicle_id, first | second)
        self.assertEqual(self._loans(po, self.byd)[0].vehicle_id, first)

    def test_two_lines_of_same_product_keep_their_own_schedules(self):
        po = self._po([(self.byd, 1), (self.byd, 1)])
        first_line, second_line = po.order_line.sorted('id')
        vehicle = self._units(self.byd, 1)
        self._move(second_line, vehicle)._sync_leasing_vehicles()
        loans = po.leasing_loan_ids
        self.assertEqual(loans.filtered(lambda loan: loan.purchase_line_id == second_line).vehicle_id, vehicle)
        self.assertFalse(loans.filtered(lambda loan: loan.purchase_line_id == first_line).vehicle_id)

    def test_schedule_without_po_line_is_matched_by_variant(self):
        po = self._po([(self.honda, 1)])
        loan = po.leasing_loan_ids
        loan.purchase_line_id = False
        vehicle = self._units(self.honda, 1)
        self._move(po.order_line, vehicle)._sync_leasing_vehicles()
        self.assertEqual(loan.vehicle_id, vehicle)

    def test_vehicle_already_on_a_schedule_is_not_given_twice(self):
        po = self._po([(self.byd, 2)])
        vehicle = self._units(self.byd, 1)
        receipt = self._move(po.order_line, vehicle)
        receipt._sync_leasing_vehicles()
        receipt._sync_leasing_vehicles()
        self.assertEqual(len(po.leasing_loan_ids.filtered('vehicle_id')), 1)

    def test_return_empties_draft_schedule_and_replacement_fills_it(self):
        po = self._po([(self.byd, 1)])
        loan = po.leasing_loan_ids
        returned = self._units(self.byd, 1)
        receipt = self._move(po.order_line, returned)
        receipt._sync_leasing_vehicles()
        self.assertEqual(loan.vehicle_id, returned)

        self._move(po.order_line, returned, returned=receipt)._sync_leasing_vehicles()
        self.assertFalse(loan.vehicle_id)

        replacement = self._units(self.byd, 1)
        self._move(po.order_line, replacement)._sync_leasing_vehicles()
        self.assertEqual(loan.vehicle_id, replacement)

    def test_return_keeps_vehicle_of_running_schedule_and_reports_it(self):
        po = self._po([(self.byd, 1)])
        vehicle = self._units(self.byd, 1)
        receipt = self._move(po.order_line, vehicle)
        loan = self._loan(count=1, purchase_order_id=po.id, purchase_line_id=po.order_line.id, vehicle_id=vehicle.id)
        self.assertEqual(loan.state, 'running')
        messages = loan.message_ids

        self._move(po.order_line, vehicle, returned=receipt)._sync_leasing_vehicles()
        self.assertEqual(loan.vehicle_id, vehicle)
        self.assertIn('diretur', (loan.message_ids - messages).body)
