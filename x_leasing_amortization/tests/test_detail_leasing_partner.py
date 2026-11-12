from lxml import etree

from odoo.tests import tagged

from .test_early_settlement import LeasingScheduleCommon


@tagged('post_install', '-at_install')
class TestLeasingDetailPartner(LeasingScheduleCommon):
    def test_detail_reads_partner_from_po_not_vendor_or_manual_loan_bank(self):
        partner = self.env['res.partner'].create({'name': 'Detail PO Leasing Partner', 'is_company': True})
        manual = self.env['res.partner'].create({'name': 'Manual Header Partner', 'is_company': True})
        self.po.leasing_partner_id = partner
        loan = self._loan(count=2, purchase_order_id=self.po.id, bank_id=manual.id)
        self.assertEqual(loan.line_ids.leasing_partner_id, partner)
        self.assertEqual(loan.line_ids.vendor_id, self.vendor)
        self.assertEqual(loan.bank_id, manual)
        self.assertEqual(loan.line_ids._fields['leasing_partner_id'].comodel_name, 'res.partner')

    def test_po_partner_changes_refresh_existing_running_detail_without_financial_changes(self):
        loan = self._loan(count=2, purchase_order_id=self.po.id, state='running')
        lines = loan.line_ids
        before = lines.read(['date', 'principal', 'interest', 'payment', 'vendor_id', 'vendor_bill_id'])
        partner = self.env['res.partner'].create({'name': 'Updated PO Leasing Partner', 'is_company': True})
        self.po.leasing_partner_id = partner
        self.assertEqual(lines.leasing_partner_id, partner)
        self.assertEqual(lines.read(list(before[0])), before)
        self.assertEqual(loan.vendor_id, self.vendor)
        self.assertEqual(loan.bank_id, self.vendor)
        self.po.leasing_partner_id = False
        self.assertFalse(lines.leasing_partner_id)
        self.assertEqual(lines.read(list(before[0])), before)

    def test_manual_schedule_without_po_has_no_po_leasing_partner(self):
        loan = self._loan(count=2, purchase_order_id=False, bank_id=self.vendor.id)
        self.assertFalse(loan.purchase_order_id)
        self.assertFalse(loan.line_ids.leasing_partner_id)

    def test_partner_is_stored_and_searchable_for_each_po(self):
        partner = self.env['res.partner'].create({'name': 'Other PO Leasing Partner', 'is_company': True})
        other = self.po.copy({'leasing_partner_id': partner.id})
        first = self._loan(count=2, purchase_order_id=self.po.id)
        second = self._loan(count=2, purchase_order_id=other.id)
        lines = first.line_ids | second.line_ids
        found = self.env['account.loan.line'].search([
            ('id', 'in', lines.ids), ('leasing_partner_id', '=', partner.id),
        ])
        self.assertEqual(found, second.line_ids.sorted('date'))
        self.assertTrue(lines._fields['leasing_partner_id'].store)
        self.assertTrue(lines._fields['leasing_partner_id'].readonly)

    def test_partner_is_present_in_table_list_and_detail_form(self):
        model = self.env['account.loan.line']
        view = self.env.ref('x_leasing_amortization.account_loan_line_global_list_view')
        arch = etree.fromstring(model.get_view(view_id=view.id, view_type='list')['arch'])
        self.assertEqual(len(arch.xpath("//field[@name='leasing_partner_id']")), 1)
        form = etree.fromstring(model.get_view(view_type='form')['arch'])
        self.assertEqual(len(form.xpath("//field[@name='leasing_partner_id']")), 1)
