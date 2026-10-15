import importlib.util
from pathlib import Path

from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestRpcMarketingProfitability(TransactionCase):
    """Profitability takes final PIC Internal, not accumulated MK01-MK04."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context={
            **cls.env.context,
            'tracking_disable': True,
            'mail_create_nosubscribe': True,
        })
        cls.partner = cls.env['res.partner'].create({'name': 'RPC PIC Internal Test'})
        cls.province = cls.env.ref('x_rental_profit_calculation.prov_dki')
        cls.city = cls.env['rpc.kota'].create({
            'name': 'RPC PIC Internal City', 'provinsi_id': cls.province.id,
        })
        cls.parameters = {
            field: cls.env['rpc.parameter'].create({
                'name': 'PIC Test ' + parameter_type,
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
            'pic_internal': 1000000,
            **overrides,
        })

    def _values(self, document):
        return {line['component']: line for line in document._rpc_profitability_values()}

    def _legacy_funding(self, document):
        hierarchy = self.env['rpc.funding.hierarchy.1'].search([
            ('name', '=', 'AKUMULASI/UNIT'),
        ], limit=1) or self.env['rpc.funding.hierarchy.1'].create({'name': 'AKUMULASI/UNIT'})
        marketing = self.env['rpc.funding.hierarchy.2'].search([
            ('hierarchy_1_id', '=', hierarchy.id), ('name', '=', 'MARKETING & KOMISI'),
        ], limit=1) or self.env['rpc.funding.hierarchy.2'].create({
            'name': 'MARKETING & KOMISI', 'hierarchy_1_id': hierarchy.id,
        })
        for model, amount in (
            ('rpc.document.funding.needs.batas.atas', 37500000),
            ('rpc.document.funding.needs.batas.bawah', 99000000),
        ):
            self.env[model].create({
                'document_id': document.id,
                'hierarchy_1_id': hierarchy.id,
                'hierarchy_2_id': marketing.id,
                'tahun_1': 6500000,
                'tahun_2': 19000000,
                'tahun_3': amount,
                'total': amount,
            })

    def _migration(self):
        path = Path(__file__).parent.parent / 'migrations' / '19.0.1.0.108' / 'post-migrate.py'
        spec = importlib.util.spec_from_file_location('rpc_final_pic_upgrade', path)
        migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(migration)
        return migration

    def test_final_pic_36_months_is_18_5_million(self):
        document = self._document()
        marketing = self._values(document)['marketing']
        self.assertEqual(marketing['batas_atas'], 18500000)
        self.assertEqual(marketing['batas_bawah'], 18500000)
        self.assertIn('PIC Internal tahun terakhir', marketing['formula'])
        # The Marketing tab's separate header total keeps its existing formula.
        self.assertEqual(document.total_biaya_marketing, 36000000)

    def test_last_tenor_including_partial_year(self):
        for months, expected in (
            (1, 1000000), (12, 6500000), (24, 12500000),
            (26, 13500000), (36, 18500000), (48, 24500000), (60, 30500000),
        ):
            with self.subTest(months=months):
                document = self._document(masa_sewa=months)
                self.assertEqual(self._values(document)['marketing']['batas_atas'], expected)

    def test_does_not_accumulate_or_include_other_marketing_components(self):
        document = self._document(
            infrastruktur=2000000, komisi_proyek=3000000, lainnya_marketing=400000,
        )
        self._legacy_funding(document)
        before = (document.funding_needs_batas_atas_ids.read(),
                  document.funding_needs_batas_bawah_ids.read())
        document._generate_rpc_profitability_lines()
        marketing = document.rpc_profitability_line_ids.filtered(lambda line: line.component == 'marketing')
        self.assertEqual(marketing.batas_atas, 18500000)
        self.assertEqual(marketing.batas_bawah, 18500000)
        self.assertEqual(before, (document.funding_needs_batas_atas_ids.read(),
                                  document.funding_needs_batas_bawah_ids.read()))
        self.assertEqual(document.total_biaya_marketing, 55400000)

    def test_zero_pic_has_no_fallback_to_old_accumulation_or_header(self):
        document = self._document(pic_internal=0, infrastruktur=2000000, komisi_proyek=3000000)
        self._legacy_funding(document)
        marketing = self._values(document)['marketing']
        self.assertEqual(marketing['batas_atas'], 0)
        self.assertEqual(marketing['batas_bawah'], 0)
        self.assertEqual(document.total_biaya_marketing, 5000000)

    def test_no_rental_tenor_has_no_pic_cost(self):
        document = self._document(masa_sewa=0)
        self.assertEqual(self._values(document)['marketing']['batas_atas'], 0)
        document._generate_rpc_profitability_lines()
        self.assertFalse(document.rpc_profitability_line_ids)

    def test_marketing_is_per_unit_and_only_project_profit_multiplies_qty(self):
        single = self._values(self._document())
        multiple = self._values(self._document(jumlah_unit=4))
        for field in ('batas_atas', 'batas_bawah'):
            self.assertEqual(multiple['marketing'][field], 18500000)
            self.assertEqual(multiple['total_cost'][field], single['total_cost'][field])
            self.assertEqual(multiple['profit_total_project'][field], single['profit_per_unit'][field] * 4)

    def test_totals_profits_and_ratios_use_final_pic(self):
        document = self._document()
        values = self._values(document)
        for field in ('batas_atas', 'batas_bawah'):
            with self.subTest(limit=field):
                costs = sum(line[field] for line in values.values()
                            if line['section'] == 'cost' and line['component'] != 'total_cost')
                self.assertAlmostEqual(values['total_cost'][field], costs)
                profit = values['total_income'][field] - costs - values['remaining_book_value'][field]
                self.assertAlmostEqual(values['profit_per_unit'][field], profit)
                self.assertAlmostEqual(values['profit_total_project'][field], profit * document.jumlah_unit)
                self.assertAlmostEqual(document['rpc_profit_rpc_' + field], profit / document.otr_final)
                self.assertAlmostEqual(values['marketing']['percentage_' + field], 18500000 / document.otr_final)

    def test_changing_pic_recomputes_summary_and_generated_lines(self):
        document = self._document()
        before = document.rpc_profit_rpc_batas_atas
        document.pic_internal = 2000000
        self.assertAlmostEqual(document.rpc_profit_rpc_batas_atas, before - 18500000 / document.otr_final)
        document._generate_rpc_profitability_lines()
        marketing = document.rpc_profitability_line_ids.filtered(lambda line: line.component == 'marketing')
        self.assertEqual(marketing.batas_atas, 37000000)

    def test_upgrade_refreshes_approved_and_archived_without_other_changes(self):
        for archived in (False, True):
            with self.subTest(archived=archived):
                document = self._document(state='approved', jumlah_unit=3, active=not archived)
                self._legacy_funding(document)
                document._generate_rpc_profitability_lines()
                lines = document.rpc_profitability_line_ids
                affected = {'marketing', 'total_cost', 'profit_per_unit', 'profit_total_project'}
                expected = {line.id: (line.batas_atas, line.batas_bawah,
                                     line.percentage_batas_atas, line.percentage_batas_bawah, line.formula)
                            for line in lines}
                untouched = lines.filtered(lambda line: line.component not in affected)
                untouched_before = untouched.read()
                funding_before = (document.funding_needs_batas_atas_ids.read(),
                                  document.funding_needs_batas_bawah_ids.read())
                # Simulate the old formula and all of its dependent totals.
                for line in lines.filtered(lambda line: line.component in affected):
                    multiplier = {'marketing': 1, 'total_cost': 1, 'profit_per_unit': -1,
                                  'profit_total_project': -3}[line.component]
                    denominator = document.otr_final * (3 if line.component == 'profit_total_project' else 1)
                    legacy_amounts = {field: line[field] + 19000000 * multiplier
                                      for field in ('batas_atas', 'batas_bawah')}
                    line.write({**legacy_amounts, **{
                        'percentage_' + field: amount / denominator
                        for field, amount in legacy_amounts.items()
                    }})
                lines.filtered(lambda line: line.component == 'marketing').formula = 'Akumulasi/Unit Marketing & Komisi tahun tenor'
                self._migration().migrate(self.cr, '19.0.1.0.107')
                lines.invalidate_recordset()
                self.assertEqual(document.rpc_profitability_line_ids.ids, lines.ids)
                for line in lines:
                    actual = (line.batas_atas, line.batas_bawah, line.percentage_batas_atas,
                              line.percentage_batas_bawah, line.formula)
                    for value, expected_value in zip(actual, expected[line.id]):
                        if isinstance(value, float):
                            self.assertAlmostEqual(value, expected_value)
                        else:
                            self.assertEqual(value, expected_value)
                self.assertEqual(untouched.read(), untouched_before)
                self.assertEqual(document.state, 'approved')
                self.assertEqual(document.active, not archived)
                self.assertEqual(document.pic_internal, 1000000)
                self.assertEqual(document.total_biaya_marketing, 108000000)
                self.assertEqual(funding_before, (document.funding_needs_batas_atas_ids.read(),
                                                 document.funding_needs_batas_bawah_ids.read()))
                once = lines.read()
                self._migration().migrate(self.cr, '19.0.1.0.107')
                lines.invalidate_recordset()
                # Repeated migration never doubles the correction or replaces rows.
                for snapshot, repeated in zip(once, lines.read()):
                    for key in set(snapshot) - {'write_date'}:
                        self.assertEqual(snapshot[key], repeated[key])

    def test_upgrade_does_not_create_profitability_for_unprocessed_documents(self):
        document = self._document()
        self._migration().migrate(self.cr, '19.0.1.0.107')
        self.assertFalse(document.rpc_profitability_line_ids)
        self.assertEqual(document.state, 'draft')

    def test_upgrade_updates_dependent_hok_results_not_hok_cost_base(self):
        document = self._document(
            state='approved', hok='yes', basis_otr='net_otr',
            resale_value_pct=0.3, buffer_hok=0.05,
        )
        document._generate_logic_table_lines()
        lines = document.hok_matrix_line_ids
        affected = lines.filtered(lambda line: (
            line.section in ('upper', 'lower')
            and line.component_code in (
                'profit_base', 'profit_amount', 'rental_per_month', 'hok_holder_portion',
            )
        ))
        self.assertTrue(affected)
        untouched = lines - affected
        untouched_before = untouched.read()
        value_fields = [f'value_{rate}' for rate in range(0, 81, 10)]
        expected = affected.read(value_fields)
        schedules = {
            field: document[field].read()
            for field in (
                'logic_table_ids', 'funding_needs_batas_atas_ids',
                'funding_needs_batas_bawah_ids', 'gapping_cost_batas_atas_ids',
                'gapping_cost_batas_bawah_ids',
            )
        }
        # Stand in for results computed with the legacy Profit RPC base.
        affected.write({field: -1 for field in value_fields})
        self._migration().migrate(self.cr, '19.0.1.0.107')
        lines.invalidate_recordset()
        self.assertEqual(document.hok_matrix_line_ids.ids, lines.ids)
        for before, after in zip(expected, affected.read(value_fields)):
            self.assertEqual(before['id'], after['id'])
            for field in value_fields:
                self.assertAlmostEqual(before[field], after[field])
        self.assertEqual(untouched.read(), untouched_before)
        for field, before in schedules.items():
            self.assertEqual(document[field].read(), before)
