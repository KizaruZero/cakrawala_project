# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class RpcIncentiveRuuRange(models.Model):
    _name = 'rpc.incentive.ruu.range'
    _description = 'RPC Incentive RUU Range'
    _order = 'sequence, id'

    name = fields.Char(string='Range RUU', required=True)
    sequence = fields.Integer(string='Urutan', default=10)
    active = fields.Boolean(string='Aktif', default=True)
    minimum = fields.Float(string='RUU Dari', digits=(16, 6))
    maximum = fields.Float(
        string='RUU Sampai', digits=(16, 6),
        help='Isi 0 jika tidak memiliki batas maksimum.',
    )
    minimum_inclusive = fields.Boolean(string='Dari Inklusif', default=True)
    maximum_inclusive = fields.Boolean(string='Sampai Inklusif', default=True)

    _unique_range = models.Constraint(
        'UNIQUE(minimum, maximum, minimum_inclusive, maximum_inclusive)',
        'Range RUU tersebut sudah tersedia.',
    )

    @api.constrains('minimum', 'maximum')
    def _check_range(self):
        for rec in self:
            if rec.minimum < 0:
                raise ValidationError(_('RUU Dari tidak boleh negatif.'))
            if rec.maximum and rec.maximum < rec.minimum:
                raise ValidationError(_('RUU Sampai tidak boleh lebih kecil dari RUU Dari.'))

    def matches(self, value):
        self.ensure_one()
        return RpcIncentiveFactor._value_in_range(
            value,
            self.minimum,
            self.maximum,
            self.minimum_inclusive,
            self.maximum_inclusive,
        )


class RpcIncentiveOtrRange(models.Model):
    _name = 'rpc.incentive.otr.range'
    _description = 'RPC Incentive OTR Range'
    _order = 'sequence, id'

    name = fields.Char(string='Range OTR', required=True)
    sequence = fields.Integer(string='Urutan', default=10)
    active = fields.Boolean(string='Aktif', default=True)
    minimum = fields.Monetary(
        string='OTR Dari', currency_field='currency_id'
    )
    maximum = fields.Monetary(
        string='OTR Sampai', currency_field='currency_id',
        help='Isi 0 jika tidak memiliki batas maksimum.',
    )
    minimum_inclusive = fields.Boolean(string='Dari Inklusif', default=True)
    maximum_inclusive = fields.Boolean(string='Sampai Inklusif', default=True)
    currency_id = fields.Many2one(
        'res.currency', string='Mata Uang', required=True,
        default=lambda self: self.env.company.currency_id,
    )

    _unique_range = models.Constraint(
        'UNIQUE(minimum, maximum, minimum_inclusive, maximum_inclusive, currency_id)',
        'Range OTR tersebut sudah tersedia.',
    )

    @api.constrains('minimum', 'maximum')
    def _check_range(self):
        for rec in self:
            if rec.minimum < 0:
                raise ValidationError(_('OTR Dari tidak boleh negatif.'))
            if rec.maximum and rec.maximum < rec.minimum:
                raise ValidationError(_('OTR Sampai tidak boleh lebih kecil dari OTR Dari.'))

    def matches(self, value):
        self.ensure_one()
        return RpcIncentiveFactor._value_in_range(
            value,
            self.minimum,
            self.maximum,
            self.minimum_inclusive,
            self.maximum_inclusive,
        )


class RpcIncentiveFactor(models.Model):
    _name = 'rpc.incentive.factor'
    _description = 'RPC Incentive Multiplier Master'
    _order = 'sequence, id'

    _DEFAULT_FACTORS = {
        # (RUU range XML ID suffix, OTR range XML ID suffix):
        # (Non Group New, Used, Extension, Replacement,
        #  Tender New, eCatalog New, eCatalog Extension)
        ('ruu_le_180', 'otr_lt_350'): (0.005, 0.005, 0.0025, 0.005, 0.00125, 0.004, 0.004),
        ('ruu_le_180', 'otr_350_750'): (0.004, 0.004, 0.002, 0.004, 0.001, 0.0032, 0.0032),
        ('ruu_le_180', 'otr_gt_750'): (0.003, 0.003, 0.0015, 0.003, 0.00075, 0.0024, 0.0024),
        ('ruu_180_200', 'otr_lt_350'): (0.006, 0.006, 0.003, 0.006, 0.0015, 0.0048, 0.0048),
        ('ruu_180_200', 'otr_350_750'): (0.005, 0.005, 0.0025, 0.005, 0.00125, 0.004, 0.004),
        ('ruu_180_200', 'otr_gt_750'): (0.004, 0.004, 0.002, 0.004, 0.001, 0.0032, 0.0032),
        ('ruu_200_220', 'otr_lt_350'): (0.013, 0.013, 0.0065, 0.013, 0.00325, 0.0104, 0.0104),
        ('ruu_200_220', 'otr_350_750'): (0.011, 0.011, 0.0055, 0.011, 0.00275, 0.0088, 0.0088),
        ('ruu_200_220', 'otr_gt_750'): (0.008, 0.008, 0.004, 0.008, 0.002, 0.0064, 0.0064),
        ('ruu_gt_220', 'otr_lt_350'): (0.015, 0.015, 0.0075, 0.015, 0.00375, 0.012, 0.012),
        ('ruu_gt_220', 'otr_350_750'): (0.013, 0.013, 0.0065, 0.013, 0.00325, 0.0104, 0.0104),
        ('ruu_gt_220', 'otr_gt_750'): (0.010, 0.010, 0.005, 0.010, 0.0025, 0.008, 0.008),
    }
    _FACTOR_INDEX = {
        ('non_group', 'new'): 0,
        ('non_group', 'used'): 1,
        ('non_group', 'extension'): 2,
        ('non_group', 'replacement'): 3,
        ('tender', 'new'): 4,
        ('ecatalog', 'new'): 5,
        ('ecatalog', 'extension'): 6,
    }

    name = fields.Char(
        string='Nama', compute='_compute_name', store=True, readonly=True
    )
    sequence = fields.Integer(string='Urutan', default=10)
    active = fields.Boolean(string='Aktif', default=True)
    type_of_klien_id = fields.Many2one(
        'rpc.parameter', string='Type Klien', ondelete='restrict',
        domain=[('parameter_type', '=', 'type_of_klien')], required=True,
    )
    sumber_id = fields.Many2one(
        'rpc.parameter', string='Sumber', ondelete='restrict',
        domain=[('parameter_type', '=', 'sumber')], required=True,
    )
    jenis_transaksi_id = fields.Many2one(
        'rpc.parameter', string='Jenis Transaksi', ondelete='restrict',
        domain=[('parameter_type', '=', 'jenis_transaksi')], required=True,
    )
    ruu_side = fields.Selection([
        ('batas_atas', 'Batas Atas'),
        ('batas_bawah', 'Batas Bawah'),
    ], string='RUU Batas', required=True, index=True)
    ruu_range_id = fields.Many2one(
        'rpc.incentive.ruu.range', string='Range RUU', ondelete='restrict',
        required=True,
    )
    otr_range_id = fields.Many2one(
        'rpc.incentive.otr.range', string='Range OTR', ondelete='restrict',
        required=True,
    )
    factor = fields.Float(string='Faktor Pengali', digits=(16, 6))

    _unique_rule = models.Constraint(
        'UNIQUE(type_of_klien_id, sumber_id, jenis_transaksi_id, '
        'ruu_side, ruu_range_id, otr_range_id)',
        'Kombinasi Faktor Pengali tersebut sudah tersedia.',
    )

    @api.depends(
        'type_of_klien_id.name', 'sumber_id.name', 'jenis_transaksi_id.name',
        'ruu_side', 'ruu_range_id.name', 'otr_range_id.name',
    )
    def _compute_name(self):
        side_labels = dict(self._fields['ruu_side'].selection)
        for rec in self:
            rec.name = ' | '.join(filter(None, (
                rec.type_of_klien_id.name,
                rec.sumber_id.name,
                rec.jenis_transaksi_id.name,
                side_labels.get(rec.ruu_side),
                rec.ruu_range_id.name,
                rec.otr_range_id.name,
            )))

    @api.constrains(
        'type_of_klien_id', 'sumber_id', 'jenis_transaksi_id',
        'ruu_side', 'ruu_range_id', 'otr_range_id', 'factor',
    )
    def _check_values(self):
        required_fields = (
            'type_of_klien_id', 'sumber_id', 'jenis_transaksi_id',
            'ruu_side', 'ruu_range_id', 'otr_range_id',
        )
        expected_parameter_types = {
            'type_of_klien_id': 'type_of_klien',
            'sumber_id': 'sumber',
            'jenis_transaksi_id': 'jenis_transaksi',
        }
        for rec in self:
            if any(not rec[field_name] for field_name in required_fields):
                raise ValidationError(_('Semua dropdown Faktor Pengali wajib diisi.'))
            for field_name, parameter_type in expected_parameter_types.items():
                if rec[field_name].parameter_type != parameter_type:
                    raise ValidationError(_(
                        '%(field)s harus menggunakan parameter bertipe %(type)s.',
                        field=rec._fields[field_name].string,
                        type=parameter_type,
                    ))
            if rec.factor < 0:
                raise ValidationError(_('Faktor Pengali tidak boleh negatif.'))

    @staticmethod
    def _value_in_range(value, minimum, maximum, minimum_inclusive, maximum_inclusive):
        minimum_match = value >= minimum if minimum_inclusive else value > minimum
        if not minimum_match:
            return False
        if not maximum:
            return True
        return value <= maximum if maximum_inclusive else value < maximum

    @staticmethod
    def _parameter_value(parameter):
        if not parameter:
            return ''
        raw_value = ' '.join(filter(None, (parameter.name, parameter.code)))
        return ''.join(character for character in raw_value.upper() if character.isalnum())

    @api.model
    def _source_category(self, source):
        source_value = self._parameter_value(source)
        if 'TENDER' in source_value:
            return 'tender'
        if 'ECATALOG' in source_value:
            return 'ecatalog'
        return 'non_group' if source_value else False

    @api.model
    def _transaction_category(self, transaction):
        transaction_value = self._parameter_value(transaction)
        if 'REPLACEMENT' in transaction_value:
            return 'replacement'
        if 'EXTENSION' in transaction_value or 'EXTENTION' in transaction_value:
            return 'extension'
        if 'USED' in transaction_value:
            return 'used'
        if 'NEW' in transaction_value:
            return 'new'
        return False

    @api.model
    def get_factor(
        self, ruu_side, ruu_value, otr_final, source, client_type, transaction
    ):
        if not all((ruu_side, source, client_type, transaction)):
            return 0.0
        rules = self.search([
            ('active', '=', True),
            ('ruu_side', '=', ruu_side),
            ('sumber_id', '=', source.id),
            ('type_of_klien_id', '=', client_type.id),
            ('jenis_transaksi_id', '=', transaction.id),
            ('ruu_range_id.active', '=', True),
            ('otr_range_id.active', '=', True),
        ], order='sequence, id')
        matching_rule = rules.filtered(
            lambda rule: (
                rule.ruu_range_id.matches(ruu_value)
                and rule.otr_range_id.matches(otr_final)
            )
        )[:1]
        return matching_rule.factor if matching_rule else 0.0

    @api.model
    def _find_or_create_parameter(self, parameter_type, category, default_name):
        parameters = self.env['rpc.parameter'].with_context(active_test=False).search([
            ('parameter_type', '=', parameter_type),
        ])
        classifier = (
            self._source_category
            if parameter_type == 'sumber'
            else self._transaction_category
        )
        parameter = parameters.filtered(
            lambda rec: classifier(rec) == category
        )[:1]
        if parameter:
            if not parameter.active:
                parameter.active = True
            return parameter
        return self.env['rpc.parameter'].create({
            'name': default_name,
            'code': category.upper(),
            'parameter_type': parameter_type,
        })

    @api.model
    def _non_captive_client_types(self):
        parameters = self.env['rpc.parameter'].with_context(active_test=False).search([
            ('parameter_type', '=', 'type_of_klien'),
        ])
        non_captive = parameters.filtered(
            lambda rec: 'NONCAPTIVE' in self._parameter_value(rec)
        )
        if not non_captive:
            non_captive = self.env['rpc.parameter'].create({
                'name': 'NON CAPTIVE',
                'code': 'NON_CAPTIVE',
                'parameter_type': 'type_of_klien',
            })
        return non_captive

    @api.model
    def _legacy_factor_values(self):
        """Read the former wide matrix so customized values survive this upgrade."""
        legacy_columns = (
            'ruu_min', 'ruu_max', 'ruu_min_inclusive', 'ruu_max_inclusive',
            'otr_min', 'otr_max', 'otr_min_inclusive', 'otr_max_inclusive',
            'non_group_new_factor', 'non_group_used_factor',
            'non_group_extension_factor', 'non_group_replacement_factor',
            'tender_new_factor', 'ecatalog_new_factor',
            'ecatalog_extension_factor',
        )
        self.env.cr.execute(
            """SELECT column_name
                 FROM information_schema.columns
                WHERE table_name = 'rpc_incentive_factor'
                  AND column_name = ANY(%s)""",
            [list(legacy_columns)],
        )
        available_columns = {row[0] for row in self.env.cr.fetchall()}
        if not set(legacy_columns).issubset(available_columns):
            return {}

        self.env.cr.execute(
            'SELECT %s FROM rpc_incentive_factor '
            'WHERE type_of_klien_id IS NULL' % ', '.join(legacy_columns)
        )
        legacy_values = {}
        for row in self.env.cr.fetchall():
            values = dict(zip(legacy_columns, row))
            ruu_range = self.env['rpc.incentive.ruu.range'].search([
                ('minimum', '=', values['ruu_min']),
                ('maximum', '=', values['ruu_max']),
                ('minimum_inclusive', '=', values['ruu_min_inclusive']),
                ('maximum_inclusive', '=', values['ruu_max_inclusive']),
            ], limit=1)
            otr_range = self.env['rpc.incentive.otr.range'].search([
                ('minimum', '=', values['otr_min']),
                ('maximum', '=', values['otr_max']),
                ('minimum_inclusive', '=', values['otr_min_inclusive']),
                ('maximum_inclusive', '=', values['otr_max_inclusive']),
            ], limit=1)
            if not ruu_range or not otr_range:
                continue
            legacy_values[(ruu_range.id, otr_range.id)] = (
                values['non_group_new_factor'],
                values['non_group_used_factor'],
                values['non_group_extension_factor'],
                values['non_group_replacement_factor'],
                values['tender_new_factor'],
                values['ecatalog_new_factor'],
                values['ecatalog_extension_factor'],
            )
        return legacy_values

    @api.model
    def _ensure_default_rules(self):
        """Create normalized defaults on install and migrate the former matrix."""
        range_pairs = {}
        for (ruu_suffix, otr_suffix), default_factors in self._DEFAULT_FACTORS.items():
            ruu_range = self.env.ref(
                f'x_rental_profit_calculation.incentive_{ruu_suffix}'
            )
            otr_range = self.env.ref(
                f'x_rental_profit_calculation.incentive_{otr_suffix}'
            )
            range_pairs[(ruu_range.id, otr_range.id)] = default_factors

        legacy_values = self._legacy_factor_values()
        if legacy_values:
            range_pairs.update(legacy_values)

        legacy_rules = self.search([
            ('type_of_klien_id', '=', False),
        ])
        if legacy_rules:
            self.env['ir.model.data'].search([
                ('model', '=', self._name),
                ('res_id', 'in', legacy_rules.ids),
            ]).unlink()
            legacy_rules.unlink()

        client_types = self._non_captive_client_types()
        source_by_category = {
            category: self._find_or_create_parameter('sumber', category, name)
            for category, name in (
                ('non_group', 'NON GROUP'),
                ('tender', 'TENDER'),
                ('ecatalog', 'eCATALOG'),
            )
        }
        transaction_by_category = {
            category: self._find_or_create_parameter(
                'jenis_transaksi', category, name
            )
            for category, name in (
                ('new', 'REGULER - NEW'),
                ('used', 'REGULER - USED'),
                ('extension', 'REGULER - EXTENSION'),
                ('replacement', 'REGULER - REPLACEMENT'),
            )
        }

        sequence = 10
        for client_type in client_types:
            for (source_category, transaction_category), factor_index in self._FACTOR_INDEX.items():
                source = source_by_category[source_category]
                transaction = transaction_by_category[transaction_category]
                for ruu_side in ('batas_atas', 'batas_bawah'):
                    for (ruu_range_id, otr_range_id), factors in range_pairs.items():
                        domain = [
                            ('type_of_klien_id', '=', client_type.id),
                            ('sumber_id', '=', source.id),
                            ('jenis_transaksi_id', '=', transaction.id),
                            ('ruu_side', '=', ruu_side),
                            ('ruu_range_id', '=', ruu_range_id),
                            ('otr_range_id', '=', otr_range_id),
                        ]
                        rule = self.search(domain, limit=1)
                        if not rule:
                            self.create({
                                'sequence': sequence,
                                'type_of_klien_id': client_type.id,
                                'sumber_id': source.id,
                                'jenis_transaksi_id': transaction.id,
                                'ruu_side': ruu_side,
                                'ruu_range_id': ruu_range_id,
                                'otr_range_id': otr_range_id,
                                'factor': factors[factor_index],
                            })
                        sequence += 10

        # A direct upgrade from the former wide table temporarily contains
        # legacy rows without these values while the registry is initialized.
        # After conversion, enforce the same database invariant as required=True.
        for column_name in (
            'type_of_klien_id', 'sumber_id', 'jenis_transaksi_id',
            'ruu_side', 'ruu_range_id', 'otr_range_id',
        ):
            self.env.cr.execute(
                'ALTER TABLE rpc_incentive_factor '
                f'ALTER COLUMN {column_name} SET NOT NULL'
            )
