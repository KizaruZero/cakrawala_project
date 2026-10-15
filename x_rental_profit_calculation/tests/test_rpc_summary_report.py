import io
import os
from pathlib import Path
from unittest import SkipTest
from unittest.mock import patch

from lxml import etree, html as lxml_html

from odoo import Command
from odoo.tests import TransactionCase, tagged
from odoo.tools.pdf import PdfReader


REPORT = 'x_rental_profit_calculation.report_rpc_summary_document'


@tagged('post_install', '-at_install')
class TestRpcSummaryReport(TransactionCase):
    """Use the real QWeb/PDF renderer, with all twenty profitability rows."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if cls.env['ir.actions.report'].get_wkhtmltopdf_state() not in ('ok', 'workers'):
            raise SkipTest('RPC PDF pagination checks require wkhtmltopdf')
        cls.env = cls.env(context={
            **cls.env.context, 'tracking_disable': True,
            'mail_create_nosubscribe': True, 'lang': 'en_US',
        })
        cls.env.company.write({
            'name': 'PT CAKRAWALA RENTALINDO SEJAHTERA',
            'currency_id': cls.env.ref('base.IDR').id,
        })
        cls.partner = cls.env['res.partner'].create({'name': 'Alabama Department of Labor (AL DOL)'})
        cls.province = cls.env.ref('x_rental_profit_calculation.prov_dki')
        cls.city = cls.env['rpc.kota'].create({'name': 'Jakarta', 'provinsi_id': cls.province.id})
        cls.parameters = {
            field: cls.env['rpc.parameter'].create({
                'name': name, 'parameter_type': parameter_type,
            }).id
            for field, parameter_type, name in (
                ('type_of_klien_id', 'type_of_klien', 'CAPTIVE'),
                ('jenis_transaksi_id', 'jenis_transaksi', 'REGULER - EXTENSION'),
                ('tujuan_id', 'tujuan', 'NEW RENTAL'),
                ('sumber_id', 'sumber', 'CANVASSING'),
                ('sumber_daya_id', 'sumber_daya', 'ICE'),
                ('jenis_kendaraan_id', 'jenis_kendaraan', 'Non-Bus & Non-Truk'),
                ('pemakaian_id', 'pemakaian', 'OPERASIONAL KANTOR'),
                ('merek_id', 'merek', 'Honda CRV'),
                ('leasing_bank_id', 'leasing_bank', 'ACC'),
            )
        }

    def _document(self, **overrides):
        document = self.env['rpc.document'].create({
            **self.parameters,
            'name': 'RPC/2026/09-00024', 'partner_id': self.partner.id,
            'provinsi_id': self.province.id, 'kota_id': self.city.id,
            'type_kendaraan': 'Honda CRV', 'tahun_kendaraan': 2026,
            'masa_sewa': 60, 'tahun_mulai_sewa': 2026, 'jumlah_unit': 1,
            'term_of_payment_due': 'addb', 'term_of_payment_hari': 30,
            'sewa_per_bulan_batas_atas': 5000000,
            'sewa_per_bulan_batas_bawah': 4500000,
            'harga_otr': 50000000, 'masa_kredit': 60,
            'down_payment_pct': 0.05, 'bunga_pct': 0.05,
            'provisi_admin_pct': 0.1, 'penalti_pct': 0.1,
            'cost_of_fund_pct': 0.05, 'opex_pusat_pct': 0.05,
            'resale_value_rate': 0.03, 'biaya_towing': 1000000,
            'replacement_car_qty': 1, 'state': 'approved',
            'final_rental_price_type': 'lower', 'final_rental_price': 4500000,
            'insurance_line_ids': [Command.create({
                'sequence': year * 10, 'tahun': 2025 + year, 'rate': 0.0197,
            }) for year in range(1, 6)],
            **overrides,
        })
        document._generate_rpc_profitability_lines()
        self.assertEqual(len(document.rpc_profitability_line_ids), 20)
        return document

    def _render(self, document, name):
        report_model = type(self.env['ir.actions.report'])
        original_prepare = report_model._prepare_html
        css_cache = {}

        def inline_styles(reports, content):
            root = lxml_html.fromstring(content)
            for node in root.xpath('//link[@rel="stylesheet"]'):
                url = node.get('href')
                if url not in css_cache:
                    bundle_name, rtl, _asset_type, autoprefix = reports.env['ir.asset']._parse_bundle_name(
                        url.rsplit('/', 1)[-1], False,
                    )
                    attachments = reports.env['ir.qweb']._get_asset_bundle(
                        bundle_name, css=True, js=False, rtl=rtl, autoprefix=autoprefix,
                    ).css()
                    css_cache[url] = '\n'.join(attachment.raw.decode() for attachment in attachments)
                node.tag = 'style'
                node.attrib.clear()
                node.text = css_cache[url]
            return etree.tostring(root, encoding='unicode', method='html')

        def prepare_inline(reports, content, report_model=False):
            bodies, ids, header, footer, args = original_prepare(reports, content, report_model=report_model)
            # The test's compiled CSS attachments are not yet committed, so an
            # HTTP worker cannot fetch them. Inline those exact bytes only for
            # the test; the production report and renderer remain unchanged.
            return ([inline_styles(reports, body) for body in bodies], ids,
                    inline_styles(reports, header), inline_styles(reports, footer), args)

        with patch.object(report_model, '_prepare_html', prepare_inline):
            content, report_type = self.env['ir.actions.report'].with_context(
                force_report_rendering=True,
            )._render_qweb_pdf(REPORT, res_ids=document.ids)
        self.assertEqual(report_type, 'pdf')
        # QA exports are opt-in and never write into a user's business filestore.
        qa_dir = os.environ.get('RPC_PDF_QA_DIR')
        if qa_dir:
            Path(qa_dir, name + '.pdf').write_bytes(content)
        return PdfReader(io.BytesIO(content))

    def _assert_complete_single_page(self, reader):
        self.assertEqual(len(reader.pages), 1, 'RPC summary must remain one A4 page')
        page = reader.pages[0]
        self.assertAlmostEqual(float(page.mediabox.width), 595, delta=1)
        self.assertAlmostEqual(float(page.mediabox.height), 842, delta=1)
        text = ' '.join(page.extract_text().split())
        self.assertEqual(text, text.upper(), 'All printed text must be uppercase')
        self.assertIn('ASURANSI', text)
        self.assertNotIn('ASS', text.split())
        paperformat = self.env.ref('x_rental_profit_calculation.paperformat_rpc_summary')
        self.assertEqual(paperformat.margin_left, 10)
        self.assertEqual(paperformat.margin_right, 10)
        for label in ('RPC/2026/09-00024', 'MARKETING', 'REFERENCE',
                      'OTR AWAL', 'OTR FINAL', 'FIDUSIA',
                      'POKOK HUTANG', 'DISPOSAL RESALE VALUE', 'Insentif',
                      'PROFIT BV', 'PROFIT RPC', 'RENTAL HOK', 'PORSI INDIVIDU', 'HOK:'):
            self.assertIn(label.upper(), text)
        component_field = self.env['rpc.document.profitability.line']._fields['component']
        for _component, label in component_field._description_selection(self.env):
            self.assertIn(label.upper(), text, 'Every profitability component must be printed')

    def test_standard_summary_remains_one_complete_page(self):
        document = self._document()
        self._assert_complete_single_page(self._render(document, 'rpc-larger-font'))
        self.assertEqual(document.partner_id.name, 'Alabama Department of Labor (AL DOL)')
        self.assertEqual(document.type_kendaraan, 'Honda CRV')
        # An optional baseline makes the manual visual comparison reproducible.
        baseline_path = os.environ.get('RPC_PDF_BASELINE_TEMPLATE')
        if baseline_path:
            baseline = etree.parse(baseline_path).find('template')
            baseline.tag = 't'
            baseline.set('t-name', REPORT)
            view = self.env.ref(REPORT)
            original_arch = view.arch_db
            try:
                view.arch_db = etree.tostring(baseline, encoding='unicode')
                self._render(document, 'rpc-original-font')
            finally:
                view.arch_db = original_arch

    def test_long_names_large_amounts_and_hok_remain_one_page(self):
        self.partner.name = 'PT PELANGGAN TRANSPORTASI INDONESIA CABANG JAKARTA UTARA DAN SEKITARNYA'
        self.env['rpc.parameter'].browse(self.parameters['merek_id']).name = 'Toyota Innova Zenix'
        self.env['rpc.parameter'].browse(self.parameters['leasing_bank_id']).name = 'Adira Dinamika Multifinance'
        document = self._document(
            type_kendaraan='Toyota Innova Zenix (V 2.0 CVT, 2026)',
            reference='Perpanjangan kontrak operasional kendaraan periode 2026 sampai 2031',
            harga_otr=1500000000,
            sewa_per_bulan_batas_atas=35000000,
            sewa_per_bulan_batas_bawah=30000000,
            hok='yes', basis_otr='net_otr', resale_value_pct=0.3,
            dealer_line_ids=[Command.create({
                'description': 'PT DEALER KENDARAAN INDONESIA CABANG JAKARTA UTARA',
            })],
        )
        reader = self._render(document, 'rpc-long-content')
        self._assert_complete_single_page(reader)
        self.assertIn('SEKITARNYA', reader.pages[0].extract_text())
