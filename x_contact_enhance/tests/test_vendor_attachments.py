from lxml import etree

from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestVendorAttachments(TransactionCase):

    def test_attachments_show_for_vendors_of_any_contact_type(self):
        arch = etree.fromstring(self.env['res.partner'].get_view(self.env.ref('base.view_partner_form').id, 'form')['arch'])
        for name in ('ktp_attachment', 'surat_pernyataan_rekening_attachment'):
            group = arch.xpath("//page[@name='legal_compliance']//field[@name='%s']" % name)[0].getparent()
            self.assertEqual(group.get('name'), 'vendor_section')
            self.assertEqual(group.get('invisible'), "partner_role != 'vendor'")
