# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class RpcIncentiveFactor(models.Model):
    _name = 'rpc.incentive.factor'
    _description = 'RPC Incentive Multiplier Master'
    _order = 'sequence, id'

    # Key format:
    # (RUU From, RUU To, From Inclusive, To Inclusive,
    #  OTR From, OTR To, From Inclusive, To Inclusive)
    _DEFAULT_FACTORS = {
        (0, 0.018, True, True, 0, 350000000, True, False):
            (0.005, 0.005, 0.0025, 0.005, 0.00125, 0.004, 0.004),
        (0, 0.018, True, True, 350000000, 750000000, True, True):
            (0.004, 0.004, 0.002, 0.004, 0.001, 0.0032, 0.0032),
        (0, 0.018, True, True, 750000000, 0, False, True):
            (0.003, 0.003, 0.0015, 0.003, 0.00075, 0.0024, 0.0024),
        (0.018, 0.020, False, True, 0, 350000000, True, False):
            (0.006, 0.006, 0.003, 0.006, 0.0015, 0.0048, 0.0048),
        (0.018, 0.020, False, True, 350000000, 750000000, True, True):
            (0.005, 0.005, 0.0025, 0.005, 0.00125, 0.004, 0.004),
        (0.018, 0.020, False, True, 750000000, 0, False, True):
            (0.004, 0.004, 0.002, 0.004, 0.001, 0.0032, 0.0032),
        (0.020, 0.022, False, True, 0, 350000000, True, False):
            (0.013, 0.013, 0.0065, 0.013, 0.00325, 0.0104, 0.0104),
        (0.020, 0.022, False, True, 350000000, 750000000, True, True):
            (0.011, 0.011, 0.0055, 0.011, 0.00275, 0.0088, 0.0088),
        (0.020, 0.022, False, True, 750000000, 0, False, True):
            (0.008, 0.008, 0.004, 0.008, 0.002, 0.0064, 0.0064),
        (0.022, 0, False, True, 0, 350000000, True, False):
            (0.015, 0.015, 0.0075, 0.015, 0.00375, 0.012, 0.012),
        (0.022, 0, False, True, 350000000, 750000000, True, True):
            (0.013, 0.013, 0.0065, 0.013, 0.00325, 0.0104, 0.0104),
        (0.022, 0, False, True, 750000000, 0, False, True):
            (0.010, 0.010, 0.005, 0.010, 0.0025, 0.008, 0.008),
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
    ruu_from = fields.Float(
        string='RUU From', digits=(16, 6), required=True,
        help='Nilai disimpan sebagai rasio; contoh 1,80% ditampilkan sebagai 1,80%.',
    )
    ruu_to = fields.Float(
        string='RUU To', digits=(16, 6), required=True,
        help='Isi 0 jika tidak memiliki batas maksimum.',
    )
    ruu_from_inclusive = fields.Boolean(
        string='RUU From Inklusif', default=True
    )
    ruu_to_inclusive = fields.Boolean(
        string='RUU To Inklusif', default=True
    )
    otr_from = fields.Float(
        string='OTR From', digits=(16, 2), required=True
    )
    otr_to = fields.Float(
        string='OTR To', digits=(16, 2), required=True,
        help='Isi 0 jika tidak memiliki batas maksimum.',
    )
    otr_from_inclusive = fields.Boolean(
        string='OTR From Inklusif', default=True
    )
    otr_to_inclusive = fields.Boolean(
        string='OTR To Inklusif', default=True
    )
    factor = fields.Float(string='Faktor Pengali', digits=(16, 6))

    _unique_rule = models.Constraint(
        'UNIQUE(type_of_klien_id, sumber_id, jenis_transaksi_id, ruu_side, '
        'ruu_from, ruu_to, ruu_from_inclusive, ruu_to_inclusive, '
        'otr_from, otr_to, otr_from_inclusive, otr_to_inclusive)',
        'Kombinasi Faktor Pengali tersebut sudah tersedia.',
    )

    @api.depends(
        'type_of_klien_id.name', 'sumber_id.name', 'jenis_transaksi_id.name',
        'ruu_side', 'ruu_from', 'ruu_to', 'otr_from', 'otr_to',
    )
    def _compute_name(self):
        side_labels = dict(self._fields['ruu_side'].selection)
        for rec in self:
            rec.name = ' | '.join(filter(None, (
                rec.type_of_klien_id.name,
                rec.sumber_id.name,
                rec.jenis_transaksi_id.name,
                side_labels.get(rec.ruu_side),
                rec._format_range(rec.ruu_from, rec.ruu_to, percentage=True),
                rec._format_range(rec.otr_from, rec.otr_to),
            )))

    @staticmethod
    def _format_range(value_from, value_to, percentage=False):
        multiplier = 100 if percentage else 1
        display_from = value_from * multiplier
        display_to = value_to * multiplier
        if not value_to:
            return f'> {display_from:g}'
        return f'{display_from:g} - {display_to:g}'

    @api.constrains(
        'type_of_klien_id', 'sumber_id', 'jenis_transaksi_id', 'ruu_side',
        'ruu_from', 'ruu_to', 'otr_from', 'otr_to', 'factor',
    )
    def _check_values(self):
        expected_parameter_types = {
            'type_of_klien_id': 'type_of_klien',
            'sumber_id': 'sumber',
            'jenis_transaksi_id': 'jenis_transaksi',
        }
        for rec in self:
            for field_name, parameter_type in expected_parameter_types.items():
                if rec[field_name].parameter_type != parameter_type:
                    raise ValidationError(_(
                        '%(field)s harus menggunakan parameter bertipe %(type)s.',
                        field=rec._fields[field_name].string,
                        type=parameter_type,
                    ))
            if rec.ruu_from < 0 or rec.otr_from < 0:
                raise ValidationError(_('Nilai From tidak boleh negatif.'))
            if rec.ruu_to and rec.ruu_to < rec.ruu_from:
                raise ValidationError(_('RUU To tidak boleh lebih kecil dari RUU From.'))
            if rec.otr_to and rec.otr_to < rec.otr_from:
                raise ValidationError(_('OTR To tidak boleh lebih kecil dari OTR From.'))
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

    def _matches(self, ruu_value, otr_final):
        self.ensure_one()
        return self._value_in_range(
            ruu_value,
            self.ruu_from,
            self.ruu_to,
            self.ruu_from_inclusive,
            self.ruu_to_inclusive,
        ) and self._value_in_range(
            otr_final,
            self.otr_from,
            self.otr_to,
            self.otr_from_inclusive,
            self.otr_to_inclusive,
        )

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
        ], order='sequence, id')
        matching_rule = rules.filtered(
            lambda rule: rule._matches(ruu_value, otr_final)
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
        """Read the former wide matrix so customized values survive an upgrade."""
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
            range_key = (
                values['ruu_min'], values['ruu_max'],
                values['ruu_min_inclusive'], values['ruu_max_inclusive'],
                values['otr_min'], values['otr_max'],
                values['otr_min_inclusive'], values['otr_max_inclusive'],
            )
            legacy_values[range_key] = (
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
        """Create normalized defaults on install or convert the former matrix."""
        legacy_values = self._legacy_factor_values()
        legacy_rules = self.search([('type_of_klien_id', '=', False)])
        if legacy_rules:
            self.env['ir.model.data'].search([
                ('model', '=', self._name),
                ('res_id', 'in', legacy_rules.ids),
            ]).unlink()
            legacy_rules.unlink()

        # Existing normalized rules are user-maintained. Do not recreate or
        # overwrite defaults when this helper is called by a later migration.
        if self.search_count([]):
            self._enforce_required_columns()
            return

        range_values = dict(self._DEFAULT_FACTORS)
        range_values.update(legacy_values)
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
            for categories, factor_index in self._FACTOR_INDEX.items():
                source_category, transaction_category = categories
                source = source_by_category[source_category]
                transaction = transaction_by_category[transaction_category]
                for ruu_side in ('batas_atas', 'batas_bawah'):
                    for range_key, factors in range_values.items():
                        (
                            ruu_from, ruu_to,
                            ruu_from_inclusive, ruu_to_inclusive,
                            otr_from, otr_to,
                            otr_from_inclusive, otr_to_inclusive,
                        ) = range_key
                        self.create({
                            'sequence': sequence,
                            'type_of_klien_id': client_type.id,
                            'sumber_id': source.id,
                            'jenis_transaksi_id': transaction.id,
                            'ruu_side': ruu_side,
                            'ruu_from': ruu_from,
                            'ruu_to': ruu_to,
                            'ruu_from_inclusive': ruu_from_inclusive,
                            'ruu_to_inclusive': ruu_to_inclusive,
                            'otr_from': otr_from,
                            'otr_to': otr_to,
                            'otr_from_inclusive': otr_from_inclusive,
                            'otr_to_inclusive': otr_to_inclusive,
                            'factor': factors[factor_index],
                        })
                        sequence += 10
        self._enforce_required_columns()

    @api.model
    def _enforce_required_columns(self):
        # During direct conversion from the wide table, these columns can be
        # temporarily nullable while the registry is initialized.
        for column_name in (
            'type_of_klien_id', 'sumber_id', 'jenis_transaksi_id', 'ruu_side',
        ):
            self.env.cr.execute(
                'ALTER TABLE rpc_incentive_factor '
                f'ALTER COLUMN {column_name} SET NOT NULL'
            )
