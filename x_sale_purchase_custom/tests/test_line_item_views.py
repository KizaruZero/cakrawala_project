from lxml import etree

from odoo.tests import TransactionCase, tagged
from odoo.tools.safe_eval import safe_eval


RENTAL_COLUMNS = {
    'estimated_delivery_date', 'actual_delivery_date', 'trigger_invoice_print', 'last_invoice_date',
    'utilized_months', 'remaining_months', 'qty_returned', 'qty_returned_et', 'bastk_return_date',
    'rental_aging',
}


@tagged('post_install', '-at_install')
class TestLineItemViews(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner = cls.env['res.partner'].create({'name': 'Line Item Customer'})
        cls.product = cls.env['product.product'].create({'name': 'Line Item Product', 'type': 'consu', 'list_price': 100})

    def _order(self, **context):
        return self.env['sale.order'].with_context(**context).create({
            'partner_id': self.partner.id,
            'order_line': [
                (0, 0, {'display_type': 'line_section', 'name': 'Section'}),
                (0, 0, {'product_id': self.product.id, 'product_uom_qty': 1}),
                (0, 0, {'display_type': 'line_note', 'name': 'Note'}),
            ],
        })

    def _listed(self, action_ref):
        action = self.env.ref(action_ref)
        return self.env['sale.order.line'].search(safe_eval(action.domain))

    def _arch(self, view_ref):
        view = self.env.ref(view_ref)
        return etree.fromstring(self.env['sale.order.line'].get_view(view.id, 'list')['arch'])

    def test_sales_and_rental_lines_stay_on_their_own_menu(self):
        sale_line = self._order().order_line.filtered(lambda line: not line.display_type)
        rental_line = self._order(in_rental_app=1).order_line.filtered(lambda line: not line.display_type)
        so_lines = self._listed('x_sale_purchase_custom.action_so_line_item')
        ro_lines = self._listed('x_sale_purchase_custom.action_ro_line_item')
        self.assertIn(sale_line, so_lines)
        self.assertNotIn(rental_line, so_lines)
        self.assertIn(rental_line, ro_lines)
        self.assertNotIn(sale_line, ro_lines)

    def test_only_items_are_listed(self):
        order = self._order()
        listed = self._listed('x_sale_purchase_custom.action_so_line_item') & order.order_line
        self.assertEqual(listed.mapped('product_id'), self.product)
        self.assertEqual(len(listed), 1)
        downpayment = self.env['sale.order.line'].create({
            'order_id': order.id, 'name': 'Down Payment', 'is_downpayment': True, 'price_unit': 10, 'product_uom_qty': 0,
        })
        self.assertNotIn(downpayment, self._listed('x_sale_purchase_custom.action_so_line_item'))

    def test_every_order_status_is_listed(self):
        order = self._order()
        line = order.order_line.filtered(lambda item: not item.display_type)
        self.assertEqual(order.state, 'draft')
        self.assertIn(line, self._listed('x_sale_purchase_custom.action_so_line_item'))
        order.action_confirm()
        self.assertIn(line, self._listed('x_sale_purchase_custom.action_so_line_item'))
        order.with_context(disable_cancel_warning=True).action_cancel()
        self.assertEqual(order.state, 'cancel')
        self.assertIn(line, self._listed('x_sale_purchase_custom.action_so_line_item'))

    def test_a_row_opens_its_order_on_the_form_of_its_app(self):
        for context, view_ref in (({}, 'sale.view_order_form'), ({'in_rental_app': 1}, 'sale_renting.rental_order_primary_form_view')):
            order = self._order(**context)
            action = order.order_line.filtered(lambda line: not line.display_type).action_open_order()
            self.assertEqual((action['res_model'], action['res_id']), ('sale.order', order.id))
            self.assertEqual(action['views'], [(self.env.ref(view_ref).id, 'form')])
        for view_ref in ('x_sale_purchase_custom.view_so_line_item_list', 'x_sale_purchase_custom.view_ro_line_item_list'):
            root = self._arch(view_ref)
            self.assertEqual((root.get('action'), root.get('type')), ('action_open_order', 'object'))

    def test_rental_columns_are_on_the_rental_list_only(self):
        so_columns = {node.get('name'): node.get('string') for node in self._arch('x_sale_purchase_custom.view_so_line_item_list').xpath('//list/field')}
        ro_columns = {node.get('name'): node.get('string') for node in self._arch('x_sale_purchase_custom.view_ro_line_item_list').xpath('//list/field')}
        self.assertFalse(RENTAL_COLUMNS & set(so_columns))
        self.assertLessEqual(RENTAL_COLUMNS, set(ro_columns))
        self.assertEqual(so_columns['price_unit'], 'Unit Price')
        self.assertEqual(ro_columns['price_unit'], 'Unit Price/Month')

    def test_order_can_be_grouped_but_is_not_by_default(self):
        for action_ref in ('x_sale_purchase_custom.action_so_line_item', 'x_sale_purchase_custom.action_ro_line_item'):
            action = self.env.ref(action_ref)
            self.assertNotIn('search_default', action.context or '')
            search = etree.fromstring(self.env['sale.order.line'].get_view(action.search_view_id.id, 'search')['arch'])
            for name, field in (('order', 'order_id'), ('customer', 'order_partner_id'), ('product', 'product_id')):
                self.assertEqual(search.xpath("//filter[@name='%s']" % name)[0].get('context'), "{'group_by':'%s'}" % field if name != 'customer' else "{'group_by': 'order_partner_id'}")

    def test_menus_point_at_their_actions(self):
        self.assertEqual(self.env.ref('x_sale_purchase_custom.menu_so_line_item').action, self.env.ref('x_sale_purchase_custom.action_so_line_item'))
        self.assertEqual(self.env.ref('x_sale_purchase_custom.menu_ro_line_item').action, self.env.ref('x_sale_purchase_custom.action_ro_line_item'))
