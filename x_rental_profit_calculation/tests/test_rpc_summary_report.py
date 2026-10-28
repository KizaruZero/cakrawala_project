import io
import os
from pathlib import Path
from unittest import SkipTest
from unittest.mock import patch

from lxml import etree, html as lxml_html

from odoo import Command, fields
from odoo.tests import TransactionCase, tagged
from odoo.tests.common import new_test_user
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
                      'KETENTUAN SEWA', 'TGL RPC', 'TIPE KLIEN',
                      'KENDARAAN & LOKASI', 'PEMBELIAN', 'PEMBIAYAAN',
                      'DISKON & CASH BACK', 'AKSESORIS DLL', 'TENOR',
                      'UANG MUKA', 'SUKU BUNGA', 'PROVISI & ADM',
                      'BIAYA OPERASIONAL', 'ANGSURAN',
                      'OTR AWAL', 'OTR FINAL', 'FIDUSIA',
                      'POKOK HUTANG', 'DISPOSAL RESALE VALUE', 'Insentif',
                      'PROFIT BV', 'PROFIT RPC', 'RENTAL HOK', 'PORSI INDIVIDU', 'HOK:'):
            self.assertIn(label.upper(), text)
        component_field = self.env['rpc.document.profitability.line']._fields['component']
        for _component, label in component_field._description_selection(self.env):
            self.assertIn(label.upper(), text, 'Every profitability component must be printed')

    def _approval_history(self, document, names=None):
        names = names or ['Rina Ayu Prameswari', 'Bagus Dwi Saputra', 'Maya Lestari Wijaya']
        users = self.env['res.users']
        stages = self.env['rpc.approval.stage']
        for index, name in enumerate(names, 1):
            user = new_test_user(
                self.env, login=f'rpc_pdf_approver_{document.id}_{index}', name=name,
                groups='base.group_user,x_rental_profit_calculation.group_rpc_manager',
            )
            users |= user
            stages |= self.env['rpc.approval.stage'].create({
                'name': f'RPC PDF Approval Stage {index}',
                'sequence': 1000 + document.id * 100 + index * 10,
                'approver_id': user.id,
            })
        # Reverse creation order, so sorting must follow approval sequence.
        lines = self.env['rpc.document.approval.matrix'].create([{
            'document_id': document.id, 'approval_stage_id': stage.id,
            'sequence': stage.sequence, 'approver_id': user.id,
            'actual_approver_id': user.id, 'status': 'approved',
            'date_approved': fields.Datetime.now(),
        } for stage, user in reversed(list(zip(stages, users)))])
        return users, stages, lines.sorted('sequence')

    def _approval_note(self, document):
        content, _kind = self.env['ir.actions.report']._render_qweb_html(REPORT, document.ids)
        return lxml_html.fromstring(content).xpath('//div[@name="rpc_digital_approval"]')

    def test_digital_approval_lists_actual_full_names_in_sequence_read_only(self):
        document = self._document()
        users, stages, lines = self._approval_history(document)
        before = document.read(['state', 'next_approval_stage_id', 'final_rental_price', 'rpc_profitability_line_ids'])
        history = lines.read(['status', 'approver_id', 'actual_approver_id', 'date_approved'])
        self.assertEqual(document._rpc_digital_approver_names(), users.mapped('name'))
        note = self._approval_note(document)
        self.assertEqual(len(note), 1)
        text = ' '.join(note[0].text_content().split()).replace(' .', '.')
        self.assertEqual(text, 'RPC Telah disetujui didalam sistem secara digital oleh ' + ', '.join(users.mapped('name')) + '.')
        reader = self._render(document, 'rpc-digital-approval')
        self._assert_complete_single_page(reader)
        printed = ' '.join(reader.pages[0].extract_text().split())
        self.assertIn('RPC TELAH DISETUJUI DIDALAM SISTEM SECARA DIGITAL OLEH', printed)
        positions = [printed.index(user.name.upper()) for user in users]
        self.assertEqual(positions, sorted(positions))
        self.assertEqual(document.read(list(before[0])), before)
        self.assertEqual(lines.read(list(history[0])), history)
        # Subsequent master-data reassignment is not approval history.
        stages.approver_id = self.env.ref('base.user_admin')
        self.assertEqual(document._rpc_digital_approver_names(), users.mapped('name'))

    def test_unapproved_states_never_show_digital_approval_even_with_history(self):
        document = self._document()
        self._approval_history(document)
        for state in ('draft', 'submitted', 'procurement_done', 'operation_done',
                      'finance_done', 'waiting_approval', 'cancelled'):
            with self.subTest(state=state):
                document.state = state
                self.assertEqual(document._rpc_digital_approver_names(), [])
                self.assertFalse(self._approval_note(document))
        document.state = 'waiting_approval'
        reader = self._render(document, 'rpc-waiting-no-digital-approval')
        self._assert_complete_single_page(reader)
        self.assertNotIn('DISETUJUI DIDALAM SISTEM', reader.pages[0].extract_text())

    def test_legacy_partial_history_prints_only_available_actual_approvers(self):
        document = self._document()
        users, _stages, lines = self._approval_history(document)
        lines[0].actual_approver_id = False
        lines[2].status = 'pending'
        self.assertEqual(document._rpc_digital_approver_names(), [users[1].name])
        text = self._approval_note(document)[0].text_content()
        self.assertIn(users[1].name, text)
        self.assertNotIn(users[0].name, text)
        self.assertNotIn(users[2].name, text)

    def test_approved_without_history_keeps_statement_without_invented_names(self):
        document = self._document()
        self.assertEqual(document._rpc_digital_approver_names(), [])
        note = self._approval_note(document)[0]
        text = ' '.join(note.text_content().split()).replace(' .', '.')
        self.assertEqual(text, 'RPC Telah disetujui didalam sistem secara digital.')
        self.assertNotIn('oleh', text)

    def test_actual_delegation_archived_users_and_duplicate_people(self):
        document = self._document()
        users, _stages, lines = self._approval_history(document)
        delegate = new_test_user(self.env, login='rpc_pdf_actual_delegate', name='Intan Permata Dewi')
        lines[0].write({'delegation_id': delegate.id, 'actual_approver_id': delegate.id})
        lines[1].actual_approver_id = delegate
        users[2].active = False
        self.assertEqual(document._rpc_digital_approver_names(), [delegate.name, users[2].name])
        text = self._approval_note(document)[0].text_content()
        self.assertEqual(text.count(delegate.name), 1)
        self.assertIn(users[2].name, text)
        self.assertNotIn(users[0].name, text)
        self.assertNotIn(users[1].name, text)

    def test_real_approval_chain_only_prints_statement_after_last_approval(self):
        document = self._document(state='waiting_approval')
        users, stages, lines = self._approval_history(document)
        lines.write({'status': 'pending', 'actual_approver_id': False, 'date_approved': False})
        document.next_approval_stage_id = stages[0]
        for index, user in enumerate(users):
            document.with_user(user).with_context(rpc_skip_final_price_wizard=True).action_approve()
            if index < len(users) - 1:
                self.assertEqual(document.state, 'waiting_approval')
                self.assertFalse(self._approval_note(document))
            else:
                self.assertEqual(document.state, 'approved')
        self.assertEqual(document._rpc_digital_approver_names(), users.mapped('name'))
        self.assertTrue(self._approval_note(document))

    def test_many_long_approver_names_remain_on_one_complete_page(self):
        self.partner.name = 'PT PELANGGAN TRANSPORTASI INDONESIA CABANG JAKARTA UTARA DAN SEKITARNYA'
        document = self._document(
            type_kendaraan='Toyota Innova Zenix (V 2.0 CVT, 2026)',
            reference='Perpanjangan kontrak operasional kendaraan periode 2026 sampai 2031',
            harga_otr=1500000000, sewa_per_bulan_batas_atas=35000000,
            sewa_per_bulan_batas_bawah=30000000,
            hok='yes', basis_otr='net_otr', resale_value_pct=0.3,
        )
        names = [f'Approver Pengujian RPC Nama Lengkap Tahap {index}' for index in range(1, 9)]
        self._approval_history(document, names=names)
        reader = self._render(document, 'rpc-digital-approval-long-names')
        self._assert_complete_single_page(reader)
        text = ' '.join(reader.pages[0].extract_text().split())
        for name in names:
            self.assertIn(name.upper(), text)

    def test_approver_names_are_html_escaped(self):
        document = self._document()
        users, _stages, _lines = self._approval_history(document, names=['Approver <b>Nama</b> & Rekan'])
        note = self._approval_note(document)[0]
        self.assertIn(users.name, note.text_content())
        self.assertFalse(note.xpath('.//b'))

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

    def test_financial_labels_match_odoo_form_and_model_metadata(self):
        document_model = self.env['rpc.document']
        expected_metadata = {
            'rpc_indicator_discount_cashback': 'Diskon & Cash Back',
            'rpc_indicator_accessories': 'Aksesoris dll',
            'leasing_bank_id': 'Leasing',
            'otr_leasing': 'OTR',
            'masa_kredit': 'TENOR (Bulan)',
            'down_payment_pct': 'Uang Muka (% dari OTR)',
            'down_payment_amount': 'Uang Muka',
            'bunga_pct': 'Suku Bunga (% flat per Tahun)',
            'provisi_admin_pct': 'Provisi & Adm (%)',
            'opex_pusat_pct': 'BIAYA OPERASIONAL (% per tahun dari OTR Final)',
            'angsuran_per_bulan': 'ANGSURAN',
        }
        metadata = document_model.fields_get(list(expected_metadata), ['string'])
        for field, label in expected_metadata.items():
            with self.subTest(field=field):
                self.assertEqual(metadata[field]['string'], label)

        arch, _view = document_model._get_view(
            view_id=self.env.ref('x_rental_profit_calculation.view_rpc_document_form').id,
            view_type='form',
        )
        panel = arch.xpath('//div[@class="o_rpc_indicator_panel"]')[0]
        self.assertEqual(panel.xpath('./h5/text()'), ['PEMBELIAN', 'PEMBIAYAAN'])
        expected_indicators = {
            'rpc_indicator_discount_cashback': 'Diskon & Cash Back',
            'rpc_indicator_accessories': 'Aksesoris dll',
            'leasing_bank_id': 'Leasing', 'otr_leasing': 'OTR',
            'masa_kredit': 'TENOR', 'down_payment_pct': 'Uang Muka',
            'bunga_pct': 'Suku Bunga', 'provisi_admin_pct': 'Provisi & Adm',
            'opex_pusat_pct': 'BIAYA OPERASIONAL', 'angsuran_per_bulan': 'ANGSURAN',
        }
        for field, label in expected_indicators.items():
            with self.subTest(indicator=field):
                nodes = panel.xpath('.//field[@name="%s"]/preceding-sibling::span' % field)
                self.assertEqual(len(nodes), 1)
                self.assertEqual(nodes[0].text, label)
        for field_id, label in {
            'finance_masa_kredit': 'TENOR',
            'finance_down_payment_pct': 'Uang Muka',
            'finance_bunga_pct': 'Suku Bunga',
            'finance_provisi_admin_pct': 'Provisi & Adm %',
            'finance_opex_pusat_pct': 'BIAYA OPERASIONAL',
        }.items():
            with self.subTest(finance_input=field_id):
                self.assertEqual(arch.xpath('//label[@for="%s"]/@string' % field_id), [label])
