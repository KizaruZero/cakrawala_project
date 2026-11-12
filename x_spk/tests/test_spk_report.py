import re

from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestSpkReport(TransactionCase):

    def _text(self, spk):
        html = self.env['ir.actions.report']._render_qweb_html('x_spk.report_fleet_spk_document', spk.ids)[0].decode()
        body = re.sub(r'<(style|script).*?</\1>', '', html, flags=re.S)
        return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', body))

    def _vendor(self, **values):
        return self.env['res.partner'].create({
            'name': 'SPK Report Vendor', 'is_company': True, 'x_contact_type': 'company', 'street': 'Vendor Street 2',
            'child_ids': [(0, 0, {'name': 'Vendor Contact'})],
            **values,
        })

    def _spk(self, **values):
        brand = self.env['fleet.vehicle.model.brand'].create({'name': 'Report Brand'})
        model = self.env['fleet.vehicle.model'].create({'name': 'Report Model', 'brand_id': brand.id})
        vehicle = self.env['fleet.vehicle'].create({'model_id': model.id, 'license_plate': 'B 7 RPT'})
        return self.env['fleet.spk'].create({
            'vehicle_id': vehicle.id, 'category': 'internal', 'description': 'Report', **values,
        })

    def test_addresses_do_not_repeat_the_name_printed_above_them(self):
        company = self.env.company.partner_id
        company.write({'street': 'Company Street 1', 'city': 'Company City'})
        text = self._text(self._spk(vendor_id=self._vendor().id))
        self.assertIn('%s Company Street 1' % company.name, text)
        self.assertNotIn('%s %s' % (company.name, company.name), text)
        self.assertIn('Alamat : Vendor Street 2', text)

    def test_created_by_prints_the_chosen_employee_or_a_blank_line(self):
        blank_line = 'Nama : ____________________'
        spk = self._spk()
        self.assertFalse(spk.created_by_employee_id)
        # The unapproved Approved by box prints one blank line too.
        self.assertEqual(self._text(spk).count(blank_line), 2)
        spk.created_by_employee_id = self.env['hr.employee'].create({'name': 'Budi Santoso'})
        text = self._text(spk)
        self.assertIn('Created by, Nama : Budi Santoso', text)
        self.assertEqual(text.count(blank_line), 1)

    def test_vendor_pic_is_a_contact_of_the_vendor(self):
        vendor = self._vendor(child_ids=[
            (0, 0, {'name': 'A Delivery Address', 'type': 'delivery'}),
            (0, 0, {'name': 'Vendor Contact', 'type': 'contact'}),
        ])
        text = self._text(self._spk(vendor_id=vendor.id, pic_client='Client Person'))
        self.assertIn('%s PIC : Vendor Contact' % vendor.name, text)
        self.assertNotIn('PIC : Client Person', text)

    def test_vendor_pic_is_empty_without_a_contact(self):
        vendor = self.env['res.partner'].create({'name': 'SPK Report Person Vendor'})
        text = self._text(self._spk(vendor_id=vendor.id, pic_client='Client Person'))
        self.assertRegex(text, r'%s PIC : Catatan' % vendor.name)
