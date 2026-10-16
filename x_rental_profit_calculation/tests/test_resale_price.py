import importlib.util
from pathlib import Path

from lxml import etree

from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestRpcResalePrice(TransactionCase):
    """Exclude VAT on resale once, never again on the resulting book loss."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context={
            **cls.env.context,
            'tracking_disable': True,
            'mail_create_nosubscribe': True,
            'lang': 'en_US',
        })
        cls.env.company.currency_id = cls.env.ref('base.IDR')
        cls.partner = cls.env['res.partner'].create({'name': 'RPC Net Resale Test'})
        cls.province = cls.env.ref('x_rental_profit_calculation.prov_dki')
        cls.city = cls.env['rpc.kota'].create({
            'name': 'RPC Net Resale City', 'provinsi_id': cls.province.id,
        })
        cls.parameters = {
            field: cls.env['rpc.parameter'].create({
                'name': 'Resale Test ' + parameter_type,
                'parameter_type': parameter_type,
            }).id
            for field, parameter_type in (
                ('type_of_klien_id', 'type_of_klien'),
                ('jenis_transaksi_id', 'jenis_transaksi'),
                ('tujuan_id', 'tujuan'),
                ('sumber_id', 'sumber'),
                ('sumber_daya_id', 'sumber_daya'),
                ('jenis_kendaraan_id', 'jenis_kendaraan'),
                ('pemakaian_id', 'pemakaian'),
                ('merek_id', 'merek'),
            )
        }

    def _document(self, **overrides):
        return self.env['rpc.document'].create({
            **self.parameters,
            'partner_id': self.partner.id,
            'provinsi_id': self.province.id,
            'kota_id': self.city.id,
            'tahun_mulai_sewa': 2026,
            'masa_sewa': 36,
            'jumlah_unit': 1,
            'term_of_payment_due': 'addm',
            'term_of_payment_hari': 30,
            'sewa_per_bulan_batas_atas': 9600000,
            'sewa_per_bulan_batas_bawah': 9500000,
            'harga_otr': 451100000,
            'resale_value_rate': 0.65,
            **overrides,
        })

    def _assert_net_resale(self, document):
        expected = document.currency_id.round(
            document.otr_final * document.resale_value_rate / 1.11,
        )
        self.assertEqual(document.resale_price, expected)
        self.assertEqual(
            document.estimasi_loss_nilai_buku,
            document.currency_id.round(min(expected - document.nilai_buku, 0.0)),
        )

    def _migration(self):
        path = Path(__file__).parent.parent / 'migrations' / '19.0.1.0.111' / 'post-migrate.py'
        spec = importlib.util.spec_from_file_location('rpc_net_resale_upgrade', path)
        migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(migration)
        return migration

    def test_11_percent_is_excluded_once_and_loss_is_not_double_taxed(self):
        document = self._document()
        self.assertEqual(document.otr_final * document.resale_value_rate, 293215000)
        self._assert_net_resale(document)
        self.assertAlmostEqual(document.resale_price, 264157657.66, places=2)
        self.assertAlmostEqual(document.nilai_buku, 277238541.67, places=2)
        self.assertAlmostEqual(document.estimasi_loss_nilai_buku, -13080884.01, places=2)
        self.assertIn('di bawah Nilai Buku', document.catatan_rv)

    def test_recomputing_or_changing_sources_never_nets_an_already_net_price(self):
        document = self._document()
        original_price = document.resale_price
        for _iteration in range(2):
            document._compute_resale()
            document._compute_estimasi_loss_nilai_buku()
            self.assertEqual(document.resale_price, original_price)
            self._assert_net_resale(document)
        document.write({'harga_otr': 555000000, 'resale_value_rate': 0.5})
        self._assert_net_resale(document)
        self.assertAlmostEqual(document.resale_price, 250000000)
        self.env.flush_all()
        document.invalidate_recordset()
        self._assert_net_resale(document)

    def test_gain_and_break_even_do_not_report_a_loss(self):
        used = self.env['rpc.parameter'].create({
            'name': 'Regular-Used', 'parameter_type': 'jenis_transaksi',
        })
        for book_value in (200000000, 264157657.66):
            with self.subTest(book_value=book_value):
                document = self._document(
                    jenis_transaksi_id=used.id, sisa_nilai_buku=book_value,
                )
                self.assertEqual(document.nilai_buku, book_value)
                self._assert_net_resale(document)
                self.assertAlmostEqual(document.estimasi_loss_nilai_buku, 0)

    def test_zero_rate_and_zero_otr(self):
        document = self._document(resale_value_rate=0)
        self.assertEqual(document.resale_price, 0)
        self.assertEqual(document.estimasi_loss_nilai_buku, -document.nilai_buku)
        document = self._document(harga_otr=0)
        self.assertEqual(document.resale_price, 0)
        self.assertEqual(document.nilai_buku, 0)
        self.assertEqual(document.estimasi_loss_nilai_buku, 0)

    def test_regular_used_keeps_manual_book_value(self):
        used = self.env['rpc.parameter'].create({
            'name': 'Regular-Used', 'parameter_type': 'jenis_transaksi',
        })
        document = self._document(jenis_transaksi_id=used.id, sisa_nilai_buku=300000000)
        self.assertEqual(document.nilai_buku, 300000000)
        self._assert_net_resale(document)
        document.sisa_nilai_buku = 290000000
        self.assertEqual(document.nilai_buku, 290000000)
        self._assert_net_resale(document)

    def test_form_and_model_label_exclude_ppn(self):
        self.assertEqual(
            self.env['rpc.document']._fields['resale_price'].string,
            'Resale Price (Exclude PPN)',
        )
        view = self.env.ref('x_rental_profit_calculation.view_rpc_document_form')
        root = etree.fromstring(view.arch_db.encode())
        labels = root.xpath('//field[@name="resale_price"]/@string')
        self.assertEqual(labels, ['Resale Price (Exclude PPN)'])

    def test_upgrade_refreshes_legacy_prices_including_approved_and_archived(self):
        for state, active in (('draft', True), ('approved', True), ('approved', False)):
            with self.subTest(state=state, active=active):
                document = self._document(state=state, active=active)
                document._generate_rpc_profitability_lines()
                protected_fields = [
                    'state', 'active', 'harga_otr', 'otr_final', 'resale_value_rate',
                    'nilai_buku', 'total_accum_saat_dispose',
                    'rpc_profitability_line_ids', 'funding_needs_batas_atas_ids',
                    'funding_needs_batas_bawah_ids',
                ]
                before = document.read(protected_fields)
                profitability = document.rpc_profitability_line_ids.read()
                old_loss = document.estimasi_loss_nilai_buku
                document.write({
                    'resale_price': document.otr_final * document.resale_value_rate,
                    'catatan_rv': 'Legacy gross-price comparison',
                })
                self.env.flush_all()
                self._migration().migrate(self.cr, '19.0.1.0.110')
                document.invalidate_recordset()
                self._assert_net_resale(document)
                self.assertAlmostEqual(document.estimasi_loss_nilai_buku, old_loss)
                self.assertIn('di bawah Nilai Buku', document.catatan_rv)
                self.assertEqual(document.read(protected_fields), before)
                self.assertEqual(document.rpc_profitability_line_ids.read(), profitability)
                once = document.read([
                    'resale_price', 'catatan_rv', 'estimasi_loss_nilai_buku',
                ])
                self._migration().migrate(self.cr, '19.0.1.0.110')
                document.invalidate_recordset()
                self.assertEqual(document.read(list(once[0])), once)
