from odoo.tests import Form, TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestTypeDefaultProducts(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Product = cls.env['product.product']
        cls.fee, cls.tax = Product.create([{'name': 'Fee'}, {'name': 'Tax'}])
        cls.other_fee = Product.create({'name': 'Other Fee'})
        ServiceType = cls.env['fleet.service.type']
        cls.plate_type = ServiceType.search([('is_license_plate', '=', True), ('category', '=', 'contract')], limit=1)
        cls.plate_type.default_product_ids = cls.fee | cls.tax
        cls.other_type = ServiceType.create({
            'name': 'Other Document', 'category': 'contract', 'is_license_plate': False,
            'default_product_ids': [(6, 0, cls.other_fee.ids)],
        })
        brand = cls.env['fleet.vehicle.model.brand'].create({'name': 'Doc Brand'})
        cls.model = cls.env['fleet.vehicle.model'].create({'name': 'Doc Model', 'brand_id': brand.id})
        cls.analytic_plan = cls.env['account.analytic.plan'].create({'name': 'Doc Plan'})

    def _vehicle(self, plate='B 19 DOC', **vals):
        return self.env['fleet.vehicle'].create({
            'model_id': self.model.id, 'license_plate': plate, 'initial_license_plate': plate,
            'asset_number': 'DOC-%s' % plate.replace(' ', ''), **vals,
        })

    def _document(self, vehicle=None, **vals):
        return self.env['fleet.vehicle.log.contract'].create({
            'vehicle_id': (vehicle or self._vehicle()).id, 'cost_subtype_id': self.other_type.id, **vals,
        })

    def test_batch_document_carries_the_default_products(self):
        analytic = self.env['account.analytic.account'].create({'name': 'Doc Unit', 'plan_id': self.analytic_plan.id})
        vehicle = self._vehicle(analytic_account_id=analytic.id)
        vehicle.action_create_batch_document()
        document = vehicle.log_contracts.filtered(lambda item: item.cost_subtype_id == self.plate_type)
        self.assertEqual(document.state, 'open')
        self.assertEqual(document.line_ids.product_id, self.fee | self.tax)
        self.assertTrue(all(document.line_ids.mapped('is_type_default')))
        self.assertEqual(document.line_ids.analytic_account_id, analytic)

    def test_several_vehicles_each_get_their_own_lines(self):
        vehicles = self._vehicle('B 1 DOC') | self._vehicle('B 2 DOC')
        vehicles.action_create_batch_document()
        for vehicle in vehicles:
            self.assertEqual(len(vehicle.log_contracts.line_ids), 2)

    def test_lines_sent_by_the_caller_are_left_alone(self):
        document = self._document(line_ids=[(0, 0, {'product_id': self.fee.id})])
        self.assertEqual(document.line_ids.product_id, self.fee)

    def test_form_creates_each_product_once(self):
        form = Form(self.env['fleet.vehicle.log.contract'])
        form.vehicle_id = self._vehicle()
        form.cost_subtype_id = self.other_type
        document = form.save()
        self.assertEqual(document.line_ids.product_id, self.other_fee)
        self.assertEqual(len(document.line_ids), 1)

    def test_changing_the_type_on_the_form_still_swaps_the_defaults(self):
        document = self._document()
        form = Form(document)
        form.cost_subtype_id = self.plate_type
        document = form.save()
        self.assertEqual(document.line_ids.product_id, self.fee | self.tax)

    def _empty_document(self, state='open', vehicle=None):
        document = self._document(vehicle=vehicle)
        document.line_ids.unlink()
        document.state = state
        return document

    def test_mass_action_fills_empty_documents_once(self):
        document = self._empty_document()
        document.action_fill_default_products()
        self.assertEqual(document.line_ids.product_id, self.other_fee)
        document.action_fill_default_products()
        self.assertEqual(len(document.line_ids), 1)

    def test_mass_action_keeps_what_is_already_there(self):
        document = self._empty_document()
        line = self.env['fleet.contract.product.line'].create({
            'contract_id': document.id, 'product_id': self.tax.id, 'estimated_price': 500,
        })
        document.action_fill_default_products()
        self.assertEqual(document.line_ids.product_id, self.tax | self.other_fee)
        self.assertEqual(line.estimated_price, 500)
        self.assertFalse(line.is_type_default)

    def test_mass_action_skips_documents_no_longer_in_use(self):
        for state in ('expired', 'closed'):
            document = self._empty_document(state=state, vehicle=self._vehicle('B 9 %s' % state[:3].upper()))
            document.action_fill_default_products()
            self.assertFalse(document.line_ids, state)

    def test_mass_action_returns_a_notification(self):
        result = self._empty_document().action_fill_default_products()
        self.assertEqual(result['tag'], 'display_notification')
        self.assertIn('1 of 1', result['params']['message'])
