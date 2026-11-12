from odoo import Command
from odoo.tests import tagged
from odoo.tools import is_html_empty

from .test_billing_engine_invoices import RentalBillingEngineInvoiceCommon


@tagged('post_install', '-at_install')
class TestRentalTermsConditions(RentalBillingEngineInvoiceCommon):
    """Syarat dan Ketentuan is filled only on PR/PO made from a Rental Order, never on the Bill."""

    def setUp(self):
        super().setUp()
        self.order = self._order()
        self.order.company_id.purchase_fleet_terms = '<p>Syarat RO khusus</p>'
        # A PO needs its UP and No. HP, defaulted from the company.
        self.order.company_id.write({
            'po_contact_id': self.env['res.partner'].create({'name': 'UP Terms', 'phone': '0811000111'}).id,
            'po_contact_mobile': '0811000111',
        })
        self.vendor = self.env['res.partner'].create({'name': 'Dealer Terms'})
        self.fleet = self.env['product.product'].create({'name': 'Unit Fleet Terms', 'is_vehicle': True})
        employee = self.env['hr.employee'].search([('user_id', '=', self.env.uid)], limit=1)
        if not employee:
            employee = self.env['hr.employee'].create({'name': 'Terms Requester', 'user_id': self.env.uid})
        if not employee.department_id:
            employee.department_id = self.env['hr.department'].create({'name': 'Terms Department'})
        self.employee = employee
        if not self.env['purchase.request.type.master'].search([('is_default_value', '=', True)], limit=1):
            self.env['purchase.request.type.master'].create({'name': 'Terms Default', 'is_default_value': True})

    def assertTerms(self, html):
        self.assertIn('Syarat RO khusus', html or '')

    def assertNoTerms(self, html):
        self.assertTrue(is_html_empty(html), html)

    def test_rental_order_no_longer_carries_terms(self):
        self.assertNotIn('x_terms_conditions', self.env['sale.order']._fields)

    def test_po_from_rental_order_gets_the_terms_but_not_its_bills(self):
        wizard = self.env['create.po.wizard'].create({'sale_order_id': self.order.id, 'partner_id': self.vendor.id})
        po = self.env['purchase.order'].browse(wizard.action_confirm()['res_id'])
        self.assertTerms(po.note)
        self.assertNotIn('narration', po._prepare_invoice())
        down_payment = self.env['purchase.order.advance.payment'].new({})._prepare_invoice_values(
            po, 'Down Payment', 10, po.order_line[:1])
        self.assertNotIn('narration', down_payment)

    def test_pr_from_rental_order_and_the_po_from_that_pr_get_the_terms_but_not_its_bill(self):
        wizard = self.env['rental.create.pr.wizard'].create({'sale_order_id': self.order.id, 'vendor_id': self.vendor.id})
        pr = self.env['employee.purchase.requisition'].browse(wizard.action_confirm()['res_id'])
        self.assertTerms(pr.detail_description)
        pr.button_create_purchase_order()
        po = self.env['purchase.order'].search([('requisition_order_ids', 'in', pr.ids)])
        self.assertEqual(len(po), 1)
        self.assertTerms(po.note)
        self.assertNotIn('narration', po._prepare_invoice())

    def test_pr_and_po_made_directly_stay_empty_even_with_fleet_products(self):
        pr = self.env['employee.purchase.requisition'].create({
            'employee_id': self.employee.id,
            'dept_id': self.employee.department_id.id,
            'department_id': self.employee.department_id.id,
            'user_id': self.env.uid,
            'partner_id': self.vendor.id,
            'internal_reference': 'Pembelian langsung',
            'requisition_order_ids': [Command.create({'product_id': self.fleet.id, 'quantity': 1, 'estimate_price': 10})],
        })
        self.assertNoTerms(pr.detail_description)
        po = self.env['purchase.order'].create({
            'partner_id': self.vendor.id,
            'order_line': [Command.create({'product_id': self.fleet.id, 'product_qty': 1, 'price_unit': 10})],
        })
        self.assertNoTerms(po.note)
        self.assertNotIn('narration', po._prepare_invoice())
