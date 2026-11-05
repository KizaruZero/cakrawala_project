import re

from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestSpkReport(TransactionCase):

    def _text(self, spk):
        html = self.env['ir.actions.report']._render_qweb_html('x_spk.report_fleet_spk_document', spk.ids)[0].decode()
        body = re.sub(r'<(style|script).*?</\1>', '', html, flags=re.S)
        return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', body))

    def test_addresses_do_not_repeat_the_name_printed_above_them(self):
        company = self.env.company.partner_id
        company.write({'street': 'Company Street 1', 'city': 'Company City'})
        vendor = self.env['res.partner'].create({
            'name': 'SPK Report Vendor', 'is_company': True, 'x_contact_type': 'company', 'street': 'Vendor Street 2',
            'child_ids': [(0, 0, {'name': 'Vendor Contact'})],
        })
        brand = self.env['fleet.vehicle.model.brand'].create({'name': 'Report Brand'})
        model = self.env['fleet.vehicle.model'].create({'name': 'Report Model', 'brand_id': brand.id})
        vehicle = self.env['fleet.vehicle'].create({'model_id': model.id, 'license_plate': 'B 7 RPT'})
        spk = self.env['fleet.spk'].create({
            'vehicle_id': vehicle.id, 'category': 'internal', 'description': 'Report', 'vendor_id': vendor.id,
        })
        text = self._text(spk)
        self.assertIn('%s Company Street 1' % company.name, text)
        self.assertNotIn('%s %s' % (company.name, company.name), text)
        self.assertIn('Alamat : Vendor Street 2', text)
