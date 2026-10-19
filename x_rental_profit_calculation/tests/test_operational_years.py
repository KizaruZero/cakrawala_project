import importlib.util
from pathlib import Path

from odoo import Command
from odoo.exceptions import ValidationError
from odoo.tests import Form, TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestRpcOperationalYears(TransactionCase):
    """Annual STNK/Service schedules through API, form onchanges and upgrades."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context={
            **cls.env.context,
            'tracking_disable': True,
            'mail_create_nosubscribe': True,
        })
        cls.partner = cls.env['res.partner'].create({'name': 'RPC Annual Costs Test'})
        cls.province = cls.env.ref('x_rental_profit_calculation.prov_dki')
        cls.city = cls.env['rpc.kota'].create({
            'name': 'RPC Annual Costs City', 'provinsi_id': cls.province.id,
        })
        cls.parameters = {
            field: cls.env['rpc.parameter'].create({
                'name': 'Annual Costs ' + parameter_type,
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
        cls.document_model = cls.env['rpc.document']
        cls.form_view = cls.env['ir.ui.view'].create({
            'name': 'RPC annual costs onchange test',
            'model': 'rpc.document',
            'arch': '''<form>
                <field name="tahun_mulai_sewa"/>
                <field name="masa_sewa"/>
                <field name="stnk_line_ids">
                    <list editable="bottom" create="0" delete="0">
                        <field name="sequence" column_invisible="1"/>
                        <field name="tahun" readonly="1"/>
                        <field name="rate"/>
                    </list>
                </field>
                <field name="service_line_ids">
                    <list editable="bottom" create="0" delete="0">
                        <field name="sequence" column_invisible="1"/>
                        <field name="tahun" readonly="1"/>
                        <field name="rate"/>
                    </list>
                </field>
            </form>''',
        })

    def _document(self, **overrides):
        return self.document_model.create({
            **self.parameters,
            'partner_id': self.partner.id,
            'provinsi_id': self.province.id,
            'kota_id': self.city.id,
            'tahun_mulai_sewa': 2026,
            'masa_sewa': 48,
            'term_of_payment_due': 'addm',
            'term_of_payment_hari': 30,
            'sewa_per_bulan_batas_atas': 10000000,
            'sewa_per_bulan_batas_bawah': 9000000,
            'harga_otr': 828000000,
            **overrides,
        })

    def _assert_years(self, document, years):
        for field_name in ('stnk_line_ids', 'service_line_ids'):
            with self.subTest(field=field_name):
                lines = document[field_name].sorted('tahun')
                self.assertEqual(lines.mapped('tahun'), years)
                self.assertEqual(lines.mapped('sequence'), [10 * (i + 1) for i in range(len(years))])

    def test_create_48_months_from_2026(self):
        document = self._document()
        self._assert_years(document, [2026, 2027, 2028, 2029])
        for lines in (document.stnk_line_ids, document.service_line_ids):
            self.assertFalse(any(lines.mapped('rate')))
            self.assertFalse(any(lines.mapped('amount')))

    def test_partial_year_and_existing_five_year_limit(self):
        for months, count in [(1, 1), (12, 1), (13, 2), (36, 3), (49, 5), (60, 5), (72, 5)]:
            with self.subTest(months=months):
                self._assert_years(self._document(masa_sewa=months), list(range(2026, 2026 + count)))

    def test_incomplete_header_does_not_generate_or_delete_costs(self):
        for values in [{'tahun_mulai_sewa': 0}, {'masa_sewa': 0}]:
            document = self._document(**values)
            self.assertFalse(document.stnk_line_ids)
            self.assertFalse(document.service_line_ids)
        document = self._document()
        line_ids = document.stnk_line_ids.ids
        document.write({'tahun_mulai_sewa': 0})
        self.assertEqual(document.stnk_line_ids.ids, line_ids)

    def test_completing_header_generates_both_tables(self):
        document = self._document(tahun_mulai_sewa=0)
        document.write({'tahun_mulai_sewa': 2026})
        self._assert_years(document, [2026, 2027, 2028, 2029])

    def test_batch_create_does_not_mix_documents(self):
        values = self._document().copy_data()[0]
        documents = self.document_model.create([
            {**values, 'stnk_line_ids': [], 'service_line_ids': [], 'masa_sewa': 24},
            {**values, 'stnk_line_ids': [], 'service_line_ids': [], 'tahun_mulai_sewa': 2030},
        ])
        self._assert_years(documents[0], [2026, 2027])
        self._assert_years(documents[1], [2030, 2031, 2032, 2033])

    def test_preserve_unordered_rates_and_amounts(self):
        rates = {2026: 0.008, 2027: 0.01, 2028: 0.015, 2029: 0.017}
        commands = [Command.create({'tahun': year, 'rate': rates[year], 'sequence': 10})
                    for year in (2026, 2028, 2029, 2027)]
        document = self._document(stnk_line_ids=commands, service_line_ids=commands)
        self._assert_years(document, [2026, 2027, 2028, 2029])
        for field_name in ('stnk_line_ids', 'service_line_ids'):
            for line in document[field_name]:
                self.assertEqual(line.rate, rates[line.tahun])
                self.assertEqual(line.amount, document.currency_id.round(rates[line.tahun] * document.otr_final))
        self.assertEqual(document.rpc_service_rate_tahun_2, 0.01)

    def test_missing_middle_year_keeps_later_rate(self):
        document = self._document(stnk_line_ids=[
            Command.create({'tahun': 2028, 'rate': 0.015}),
        ])
        self._assert_years(document, [2026, 2027, 2028, 2029])
        self.assertEqual(document.stnk_line_ids.filtered(lambda line: line.tahun == 2028).rate, 0.015)

    def test_reload_uses_calendar_order_even_for_legacy_sequences(self):
        document = self._document()
        for field_name in ('stnk_line_ids', 'service_line_ids'):
            lines = document[field_name].sorted('tahun')
            for sequence, line in zip([10, 40, 20, 30], lines):
                line.with_context(rpc_skip_operational_year_sync=True).write({'sequence': sequence})
        document.invalidate_recordset(['stnk_line_ids', 'service_line_ids'])
        self.assertEqual(document.stnk_line_ids.mapped('tahun'), [2026, 2027, 2028, 2029])
        self.assertEqual(document.service_line_ids.mapped('tahun'), [2026, 2027, 2028, 2029])

    def test_legacy_numbered_years(self):
        document = self._document(service_line_ids=[
            Command.create({'tahun': year, 'rate': year / 1000})
            for year in [3, 1, 4, 2]
        ])
        self._assert_years(document, [2026, 2027, 2028, 2029])
        self.assertEqual(document.service_line_ids.sorted('tahun').mapped('rate'), [0.001, 0.002, 0.003, 0.004])

    def test_extend_duration_preserves_existing_costs(self):
        document = self._document(masa_sewa=24)
        first_line = document.service_line_ids.sorted('tahun')[0]
        first_line.rate = 0.008
        document.write({'masa_sewa': 48})
        self._assert_years(document, [2026, 2027, 2028, 2029])
        self.assertEqual(first_line.rate, 0.008)
        self.assertIn(first_line, document.service_line_ids)

    def test_shorten_duration_only_removes_zero_rate_rows(self):
        document = self._document()
        first_line = document.stnk_line_ids.sorted('tahun')[0]
        first_line.rate = 0.015
        document.write({'masa_sewa': 24})
        self._assert_years(document, [2026, 2027])
        self.assertEqual(first_line.rate, 0.015)

    def test_shorten_populated_year_requires_review(self):
        document = self._document()
        document.service_line_ids.filtered(lambda line: line.tahun == 2029).rate = 0.017
        with self.assertRaises(ValidationError), self.cr.savepoint():
            document.write({'masa_sewa': 24})
        self._assert_years(document, [2026, 2027, 2028, 2029])
        self.assertEqual(document.masa_sewa, 48)

    def test_change_start_year_preserves_relative_year_rates(self):
        document = self._document()
        lines = document.service_line_ids.sorted('tahun')
        for index, line in enumerate(lines):
            line.rate = (index + 1) / 1000
        document.write({'tahun_mulai_sewa': 2028})
        self._assert_years(document, [2028, 2029, 2030, 2031])
        self.assertEqual(lines.mapped('rate'), [0.001, 0.002, 0.003, 0.004])
        self.assertEqual(lines.mapped('tahun'), [2028, 2029, 2030, 2031])

    def test_onchange_populates_before_save(self):
        document = self.document_model.new({'tahun_mulai_sewa': 2026, 'masa_sewa': 48})
        document._onchange_operational_line_years()
        self._assert_years(document, [2026, 2027, 2028, 2029])
        document.service_line_ids.sorted('tahun')[0].rate = 0.008
        document.tahun_mulai_sewa = 2028
        document._onchange_operational_line_years()
        self._assert_years(document, [2028, 2029, 2030, 2031])
        self.assertEqual(document.service_line_ids.sorted('tahun')[0].rate, 0.008)
        document.masa_sewa = 24
        document._onchange_operational_line_years()
        self._assert_years(document, [2028, 2029])

    def test_form_onchange_never_writes_until_saved(self):
        document = self._document()
        lines = document.service_line_ids.sorted('tahun')
        lines[0].rate = 0.008
        with Form(document, view=self.form_view) as form:
            form.tahun_mulai_sewa = 2028
            form.tahun_mulai_sewa = 2029
            form.masa_sewa = 36
            self.assertEqual(
                [form.service_line_ids.edit(index).tahun for index in range(len(form.service_line_ids))],
                [2029, 2030, 2031],
            )
            self.assertEqual(lines[0].tahun, 2026)
        self._assert_years(document, [2029, 2030, 2031])
        self.assertEqual(lines[0].rate, 0.008)

    def test_form_can_change_year_back_before_saving(self):
        document = self._document()
        first_line = document.service_line_ids.sorted('tahun')[0]
        first_line.rate = 0.008
        with Form(document, view=self.form_view) as form:
            form.tahun_mulai_sewa = 2028
            form.tahun_mulai_sewa = 2029
            form.tahun_mulai_sewa = 2026
            self.assertEqual(form.service_line_ids.edit(0).tahun, 2026)
            self.assertEqual(form.service_line_ids.edit(0).rate, 0.008)
        self._assert_years(document, [2026, 2027, 2028, 2029])
        self.assertEqual(first_line.rate, 0.008)

    def test_regeneration_and_copy_do_not_duplicate_lines(self):
        document = self._document()
        ids = (document.stnk_line_ids.ids, document.service_line_ids.ids)
        document._sync_operational_line_years()
        document.write({'masa_sewa': 48})
        self.assertEqual((document.stnk_line_ids.ids, document.service_line_ids.ids), ids)
        copied = document.copy()
        self._assert_years(copied, [2026, 2027, 2028, 2029])
        self.assertFalse(set(document.stnk_line_ids.ids) & set(copied.stnk_line_ids.ids))

    def test_upgrade_repairs_operation_only_and_preserves_rates(self):
        operation = self._document(state='operation_done')
        approved = self._document(state='approved')
        conflict = self._document(state='operation_done')
        for document in (operation, approved, conflict):
            document.stnk_line_ids.with_context(rpc_skip_operational_year_sync=True).unlink()
            document.service_line_ids.with_context(rpc_skip_operational_year_sync=True).unlink()
        for document in (operation, approved):
            self.env['rpc.document.service.line'].with_context(rpc_skip_operational_year_sync=True).create({
                'document_id': document.id, 'tahun': 2028, 'rate': 0.015,
            })
        self.env['rpc.document.service.line'].with_context(rpc_skip_operational_year_sync=True).create({
            'document_id': conflict.id, 'tahun': 2030, 'rate': 0.017,
        })
        path = Path(__file__).parent.parent / 'migrations' / '19.0.1.0.105' / 'post-migrate.py'
        spec = importlib.util.spec_from_file_location('rpc_annual_cost_upgrade', path)
        migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(migration)
        migration.migrate(self.cr, '19.0.1.0.104')
        self._assert_years(operation, [2026, 2027, 2028, 2029])
        self.assertEqual(operation.service_line_ids.filtered(lambda line: line.tahun == 2028).rate, 0.015)
        self.assertFalse(approved.stnk_line_ids)
        self.assertEqual(approved.service_line_ids.mapped('tahun'), [2028])
        self.assertFalse(conflict.stnk_line_ids)
        self.assertEqual(conflict.service_line_ids.mapped('tahun'), [2030])
