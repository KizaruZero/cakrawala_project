from lxml import etree

from odoo.tests import Form, TransactionCase, tagged


RENTAL_COLUMNS = (
    'estimated_delivery_date', 'actual_delivery_date', 'trigger_invoice_print', 'last_invoice_date',
    'utilized_months', 'remaining_months', 'qty_returned_et', 'bastk_return_date', 'rental_aging',
)
ALWAYS_SHOWN = ('product_template_id', 'name', 'product_uom_qty', 'price_unit', 'tax_ids')


@tagged('post_install', '-at_install')
class TestSalesOrderColumns(TransactionCase):

    def _columns(self, view_ref):
        arch = self.env['sale.order'].get_view(self.env.ref(view_ref).id, 'form')['arch']
        return {
            node.get('name'): node.get('column_invisible') or ''
            for node in etree.fromstring(arch).xpath("//field[@name='order_line']/list/field")
        }

    def test_rental_columns_follow_the_order_on_both_forms(self):
        for view_ref in ('sale.view_order_form', 'sale_renting.rental_order_form_view'):
            columns = self._columns(view_ref)
            for name in RENTAL_COLUMNS:
                self.assertEqual(columns[name], 'not parent.is_rental_order', '%s: %s' % (view_ref, name))

    def test_default_columns_stay_on_sales_orders(self):
        columns = self._columns('sale.view_order_form')
        for name in ALWAYS_SHOWN:
            self.assertNotIn('is_rental_order', columns[name], name)
        self.assertEqual(columns['qty_delivered'], "parent.state != 'sale'")
        self.assertEqual(columns['qty_invoiced'], "parent.state != 'sale'")

    def test_sales_header_fields_are_left_alone(self):
        arch = self.env['sale.order'].get_view(self.env.ref('sale.view_order_form').id, 'form')['arch']
        root = etree.fromstring(arch)
        for name in ('periodic', 'order_type_id'):
            self.assertEqual(root.xpath("//field[@name='%s']" % name)[0].get('invisible'), 'is_rental_order')
        self.assertFalse(root.xpath("//field[@name='attention_up']")[0].get('invisible'))

    def test_sales_order_confirms_without_the_hidden_columns(self):
        partner = self.env['res.partner'].create({'name': 'Sales Customer'})
        product = self.env['product.product'].create({'name': 'Sales Product', 'type': 'consu', 'list_price': 100})
        form = Form(self.env['sale.order'])
        form.partner_id = partner
        with form.order_line.new() as line:
            line.product_id = product
            line.product_uom_qty = 2
        order = form.save()
        self.assertFalse(order.is_rental_order)
        order.action_confirm()
        self.assertEqual(order.state, 'sale')
        self.assertEqual(order.order_line.product_uom_qty, 2)

    def _price_label(self, view_ref):
        arch = self.env['sale.order'].get_view(self.env.ref(view_ref).id, 'form')['arch']
        return etree.fromstring(arch).xpath("//field[@name='order_line']/list/field[@name='price_unit']")[0].get('string')

    def test_price_label_is_monthly_on_rental_orders_only(self):
        self.assertEqual(self._price_label('sale_renting.rental_order_primary_form_view'), 'Unit Price/Month')
        self.assertNotEqual(self._price_label('sale.view_order_form'), 'Unit Price/Month')

    def test_rental_order_keeps_the_flag_that_shows_the_columns(self):
        order = self.env['sale.order'].with_context(in_rental_app=1).create({
            'partner_id': self.env['res.partner'].create({'name': 'Rental Customer'}).id,
        })
        self.assertTrue(order.is_rental_order)
