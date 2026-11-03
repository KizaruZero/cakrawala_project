import base64
import datetime
import io
import logging
import re

from markupsafe import Markup, escape

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

PLATE_PATTERN = r'^[A-Za-z]{1,2}\s*\d{1,4}\s*[A-Za-z]{0,3}$'
SEQUENCE_CODE = 'asset.serial.number'

# key, label, required, description, aliases (lower case, besides key and label)
COLUMNS = (
    ('fleet_number', 'Fleet Number', True,
     'Nomor seri unit (SN). Jadi Asset Number di Fleet dan nama Analytic. Contoh: CRS-00123',
     ('fn', 'sn', 'serial number', 'lot', 'asset number', 'nomor fleet', 'no fleet')),
    ('product', 'Produk', True,
     'Produk kendaraan (Is Fleet dicentang). Isi Internal Reference atau nama produk persis.',
     ('product', 'nama produk', 'item')),
    ('model', 'Model', True,
     'Model kendaraan di Fleet. Kalau nama model kembar antar merek, tulis "Merek/Model".',
     ('vehicle model', 'model kendaraan')),
    ('location', 'Lokasi Stok', True,
     'Lokasi unit sekarang, nama lengkap lokasi bertipe Internal. Contoh: WH-JK/Stock, Customers/Rental',
     ('location', 'lokasi')),
    ('license_plate', 'Plat Awal', False,
     'Plat nomor awal. Format: 1-2 huruf, 1-4 angka, 0-3 huruf. Contoh: B 1234 ABC',
     ('initial license plate', 'license plate', 'plat', 'plat nomor', 'nopol')),
    ('chassis_number', 'No. Rangka', False, 'Nomor rangka.',
     ('chassis number', 'chassis', 'no rangka', 'nomor rangka')),
    ('engine_number', 'No. Mesin', False, 'Nomor mesin.',
     ('engine number', 'engine', 'no mesin', 'nomor mesin')),
    ('color', 'Warna', False, 'Harus sudah ada di master Warna (tidak dibuat otomatis).',
     ('color', 'colour')),
    ('year', 'Tahun', False, 'Tahun kendaraan, harus sudah ada di master Tahun. Contoh: 2023',
     ('year', 'model year', 'tahun pembuatan')),
    ('state', 'Status', False,
     'Status Fleet. Kosong = status "Is First Destination" (sama seperti dari GR).',
     ('status fleet', 'fleet status')),
    ('sub_status', 'Sub Status', False,
     'Fleet Sub-Status. Status ikut Parent Status-nya bila Status dikosongkan.',
     ('fleet sub status', 'sub-status', 'substatus')),
    ('analytic_plan', 'Analytic Plan', False,
     'Plan untuk Analytic baru. Kosong = plan pertama (sama seperti dari GR).',
     ('plan', 'analytic plan')),
)
COLUMN_KEYS = tuple(c[0] for c in COLUMNS)
REQUIRED_KEYS = tuple(c[0] for c in COLUMNS if c[2])
DESCRIPTIONS = {c[0]: c[3] for c in COLUMNS}


class _DryRunRollback(Exception):
    """Raised inside the savepoint to roll everything back on purpose."""


def _norm_header(value):
    return re.sub(r'\s+', ' ', str(value or '').replace('*', '').strip().lower())


def _cell_text(value):
    if value is None:
        return ''
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    if isinstance(value, (datetime.date, datetime.datetime)):
        return value.strftime('%Y-%m-%d')
    return re.sub(r'\s+', ' ', str(value)).strip()


class FleetOpeningImport(models.TransientModel):
    _name = 'x.fleet.opening.import'
    _description = 'Import Unit Awal (Fleet Number, Analytic, Fleet, Stok)'

    state = fields.Selection(
        [('upload', 'Upload'), ('checked', 'Dicek'), ('done', 'Selesai')],
        default='upload', required=True,
    )
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)
    file = fields.Binary(string='File Excel (.xlsx)')
    filename = fields.Char()
    template_file = fields.Binary(readonly=True)
    template_filename = fields.Char(readonly=True)

    line_ids = fields.One2many('x.fleet.opening.import.line', 'wizard_id', string='Hasil per Baris')
    total_count = fields.Integer(compute='_compute_counts')
    new_count = fields.Integer(compute='_compute_counts')
    partial_count = fields.Integer(compute='_compute_counts')
    exists_count = fields.Integer(compute='_compute_counts')
    error_count = fields.Integer(compute='_compute_counts')
    summary = fields.Html(readonly=True, sanitize=False)

    lot_ids = fields.Many2many('stock.lot', string='Fleet Numbers')
    vehicle_ids = fields.Many2many('fleet.vehicle', string='Fleet')
    analytic_ids = fields.Many2many('account.analytic.account', string='Analytic Accounts',
                                    groups='analytic.group_analytic_accounting')
    quant_ids = fields.Many2many('stock.quant', string='Stok')

    @api.depends('line_ids.status')
    def _compute_counts(self):
        for wizard in self:
            statuses = wizard.line_ids.mapped('status')
            wizard.total_count = len(statuses)
            wizard.new_count = statuses.count('new')
            wizard.partial_count = statuses.count('partial')
            wizard.exists_count = statuses.count('exists')
            wizard.error_count = statuses.count('error')

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------
    def _reopen(self):
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
            'name': _('Import Unit Awal'),
        }

    def action_download_template(self):
        self.ensure_one()
        self.write({
            'template_file': base64.b64encode(self._build_template()),
            'template_filename': 'Template_Import_Unit_Awal.xlsx',
        })
        return {
            'type': 'ir.actions.act_url',
            'url': '/web/content/?model=%s&id=%s&field=template_file&filename_field=template_filename&download=true'
                   % (self._name, self.id),
            'target': 'self',
        }

    def action_check(self):
        self.ensure_one()
        self._check_access_rights_for_import()
        results, valuation, sequence_note = self._run(commit=False)
        self._store_results(results, False, valuation, sequence_note)
        return self._reopen()

    def action_import(self):
        self.ensure_one()
        self._check_access_rights_for_import()
        results, valuation, sequence_note = self._run(commit=True)
        # With an error nothing was saved: show why, stay on the checked screen.
        done = not any(r['errors'] for r in results)
        self._store_results(results, done, valuation, sequence_note)
        return self._reopen()

    def action_reset(self):
        self.ensure_one()
        self.line_ids.sudo().unlink()
        self.sudo().write({'state': 'upload', 'file': False, 'filename': False, 'summary': False,
                           'lot_ids': [(5,)], 'vehicle_ids': [(5,)], 'analytic_ids': [(5,)], 'quant_ids': [(5,)]})
        return self._reopen()

    def _open_records(self, model, records, name):
        return {
            'type': 'ir.actions.act_window',
            'res_model': model,
            'name': name,
            'view_mode': 'list,form',
            'views': [(False, 'list'), (False, 'form')],
            'domain': [('id', 'in', records.ids)],
            'context': {'active_test': False, 'create': False},
            'target': 'current',
        }

    def action_open_vehicles(self):
        return self._open_records('fleet.vehicle', self.vehicle_ids, _('Fleet hasil import'))

    def action_open_lots(self):
        return self._open_records('stock.lot', self.lot_ids, _('Fleet Number hasil import'))

    def action_open_analytics(self):
        return self._open_records('account.analytic.account', self.analytic_ids, _('Analytic hasil import'))

    def action_open_quants(self):
        return self._open_records('stock.quant', self.quant_ids, _('Stok hasil import'))

    def _check_access_rights_for_import(self):
        user = self.env.user
        if not (user.has_group('stock.group_stock_manager') and user.has_group('fleet.fleet_group_manager')):
            raise UserError(_('Import unit awal butuh hak Inventory Administrator dan Fleet Administrator.'))
        if not self.file:
            raise UserError(_('Pilih file Excel dulu.'))

    # ------------------------------------------------------------------
    # Reading the file
    # ------------------------------------------------------------------
    @api.model
    def _header_map(self):
        mapping = {}
        for key, label, _req, _desc, aliases in COLUMNS:
            for name in (key, label, *aliases):
                mapping[_norm_header(name)] = key
        return mapping

    def _read_rows(self):
        try:
            import openpyxl
        except ImportError as exc:
            raise UserError(_('Library Python openpyxl belum terpasang di server.')) from exc
        try:
            workbook = openpyxl.load_workbook(io.BytesIO(base64.b64decode(self.file)), data_only=True, read_only=True)
        except Exception as exc:
            raise UserError(_('File tidak bisa dibaca sebagai Excel (.xlsx): %s', exc)) from exc
        sheet = workbook['Unit'] if 'Unit' in workbook.sheetnames else workbook.worksheets[0]
        rows = list(sheet.iter_rows(values_only=True))
        workbook.close()

        mapping = self._header_map()
        header_index, columns = None, {}
        for index, row in enumerate(rows[:10]):
            found = {}
            for col, value in enumerate(row):
                key = mapping.get(_norm_header(value))
                if key and key not in found:
                    found[key] = col
            if 'fleet_number' in found and len(found) >= 2:
                header_index, columns = index, found
                break
        if header_index is None:
            raise UserError(_('Baris judul kolom tidak ditemukan. Pakai template dari tombol "Download Template".'))
        missing = [label for key, label, req, _d, _a in COLUMNS if req and key not in columns]
        if missing:
            raise UserError(_('Kolom wajib tidak ada di file: %s', ', '.join(missing)))

        data = []
        for index, row in enumerate(rows[header_index + 1:], start=header_index + 2):
            vals = {key: _cell_text(row[col]) if col < len(row) else '' for key, col in columns.items()}
            for key in COLUMN_KEYS:
                vals.setdefault(key, '')
            if not any(vals.values()):
                continue
            if vals['fleet_number'] == DESCRIPTIONS['fleet_number']:
                continue  # description row of the template
            data.append((index, vals))
        if not data:
            raise UserError(_('File tidak berisi data unit.'))
        return data

    # ------------------------------------------------------------------
    # Row resolution (no database writes)
    # ------------------------------------------------------------------
    def _find_one(self, model, domains, label, value, errors):
        """First domain that matches exactly one record; several matches is an error."""
        Model = self.env[model]
        for domain in domains:
            records = Model.search(domain, limit=2)
            if len(records) == 1:
                return records
            if len(records) > 1:
                shown = Model.search(domain, limit=6)
                errors.append(_('%(label)s "%(value)s" cocok dengan %(count)s data: %(names)s. '
                                'Tulis yang spesifik (untuk produk: Internal Reference).',
                                label=label, value=value, count=len(shown) if len(shown) < 6 else '5+',
                                names='; '.join(r.display_name for r in shown[:5])))
                return Model
        errors.append(_('%(label)s "%(value)s" tidak ditemukan.', label=label, value=value))
        return Model

    def _resolve_row(self, vals, seen):
        company = self.company_id
        errors, res = [], {}

        number = vals['fleet_number']
        for key in REQUIRED_KEYS:
            if not vals[key]:
                errors.append(_('%s wajib diisi.', dict((c[0], c[1]) for c in COLUMNS)[key]))
        if number:
            if number.upper() in seen:
                errors.append(_('Fleet Number %(number)s dobel di file (baris %(row)s).',
                                number=number, row=seen[number.upper()]))
        res['fleet_number'] = number

        if vals['product']:
            company_domain = [('company_id', 'in', [company.id, False])]
            vehicle = [('is_vehicle', '=', True)]
            # Fleet products first: a same-named non-fleet product must not make the unit ambiguous.
            product = self._find_one('product.product', [
                [('default_code', '=', vals['product'])] + vehicle + company_domain,
                [('name', '=ilike', vals['product'])] + vehicle + company_domain,
                [('default_code', '=', vals['product'])] + company_domain,
                [('name', '=ilike', vals['product'])] + company_domain,
            ], _('Produk'), vals['product'], errors)
            if product:
                if not product.is_vehicle:
                    errors.append(_('Produk %s bukan produk kendaraan (Is Fleet belum dicentang).', product.display_name))
                elif product.tracking != 'serial' or not product.is_storable:
                    errors.append(_('Produk %s harus storable dan tracking By Unique Serial Number.', product.display_name))
            res['product'] = product

        if vals['model']:
            brand_name, _sep, model_name = vals['model'].rpartition('/')
            model_name = model_name.strip()
            domain = [('name', '=ilike', model_name)]
            domains = []
            if brand_name.strip():
                domains.append(domain + [('brand_id.name', '=ilike', brand_name.strip())])
            else:
                brand = res.get('product') and res['product'].fleet_brand_id
                if brand:
                    domains.append(domain + [('brand_id', '=', brand.id)])
                domains.append(domain)
            found = self.env['fleet.vehicle.model']
            for dom in domains:
                found = self.env['fleet.vehicle.model'].search(dom, limit=2)
                if found:
                    break
            if len(found) > 1:
                errors.append(_('Model "%s" ada di lebih dari satu merek: tulis "Merek/Model".', vals['model']))
                found = found.browse()
            elif not found:
                errors.append(_('Model "%s" tidak ditemukan di Fleet.', vals['model']))
            res['model'] = found

        if vals['location']:
            company_domain = [('company_id', 'in', [company.id, False])]
            location = self._find_one('stock.location', [
                [('complete_name', '=ilike', vals['location'])] + company_domain,
                [('barcode', '=', vals['location'])] + company_domain,
            ], _('Lokasi'), vals['location'], errors)
            if location and location.usage != 'internal':
                errors.append(_('Lokasi %s bukan tipe Internal: unit di sana tidak terbaca BASTK / Replacement Car.',
                                location.complete_name))
            res['location'] = location

        plate = vals['license_plate']
        if plate:
            plate = self.env['stock.move.line'].format_license_plate_input(plate)
            if not re.match(PLATE_PATTERN, plate):
                errors.append(_('Plat "%s" formatnya salah. Contoh benar: B 1234 ABC.', vals['license_plate']))
        res['license_plate'] = plate or False
        res['chassis_number'] = vals['chassis_number'] or False
        res['engine_number'] = vals['engine_number'] or False

        res['color'] = self.env['vehicle.color']
        if vals['color']:
            res['color'] = self._find_one('vehicle.color', [[('name', '=ilike', vals['color'])]],
                                          _('Warna'), vals['color'], errors)
        res['year'] = self.env['vehicle.year']
        if vals['year']:
            res['year'] = self._find_one('vehicle.year', [[('name', '=ilike', vals['year'])]],
                                         _('Tahun'), vals['year'], errors)
            if res['year'] and not self.env['stock.lot']._is_valid_model_year(res['year'].name):
                errors.append(_('Tahun %s tidak valid untuk Model Year di Fleet.', res['year'].name))

        state = self.env['fleet.vehicle.state']
        if vals['state']:
            state = self._find_one('fleet.vehicle.state', [[('name', '=ilike', vals['state'])]],
                                   _('Status'), vals['state'], errors)
        sub_status = self.env['vehicle.substatus']
        if vals['sub_status']:
            sub_status = self._find_one('vehicle.substatus', [[('name', '=ilike', vals['sub_status'])]],
                                        _('Sub Status'), vals['sub_status'], errors)
            parent = sub_status.state_id
            if parent and state and parent != state:
                errors.append(_('Sub Status %(sub)s milik Status %(parent)s, bukan %(state)s.',
                                sub=sub_status.name, parent=parent.name, state=state.name))
            state = state or parent
        if not state:
            state = self.env['fleet.vehicle.state'].search([('is_first_destination', '=', True)], limit=1)
        if state and 'is_inactive_state' in state._fields and state.is_inactive_state:
            errors.append(_('Status %s adalah status nonaktif (mis. Sold): unit seperti ini tidak perlu dinaikkan stoknya.',
                            state.name))
        res['state'] = state
        res['sub_status'] = sub_status

        if vals['analytic_plan']:
            res['plan'] = self.sudo()._find_one('account.analytic.plan', [[('name', '=ilike', vals['analytic_plan'])]],
                                         _('Analytic Plan'), vals['analytic_plan'], errors)
        else:
            res['plan'] = self.env['account.analytic.plan'].sudo().search([], limit=1)
            if not res['plan']:
                errors.append(_('Belum ada Analytic Plan sama sekali.'))
        return res, errors

    # ------------------------------------------------------------------
    # Row processing (database writes)
    # ------------------------------------------------------------------
    def _process_row(self, res):
        """Create or reuse lot, analytic, vehicle and stock of one unit.

        Returns (notes, created, records); raises UserError for a blocking problem.
        """
        company = self.company_id
        Lot = self.env['stock.lot']
        Vehicle = self.env['fleet.vehicle'].with_context(active_test=False)
        Analytic = self.env['account.analytic.account'].sudo()
        Quant = self.env['stock.quant']
        number, product = res['fleet_number'], res['product']
        notes, created = [], set()

        # 1. Fleet Number (stock.lot)
        lot_vals = {
            'chassis_number': res['chassis_number'],
            'engine_number': res['engine_number'],
            'vehicle_model_id': res['model'].id,
            'vehicle_year_id': res['year'].id or False,
            'vehicle_color_id': res['color'].id or False,
        }
        lot = Lot.search([('name', '=', number), ('product_id.is_vehicle', '=', True),
                          ('company_id', 'in', [company.id, False])], limit=1)
        if lot:
            if lot.product_id != product:
                raise UserError(_('Fleet Number %(number)s sudah ada untuk produk %(product)s.',
                                  number=number, product=lot.product_id.display_name))
            fill = {k: v for k, v in lot_vals.items() if v and not lot[k]}
            if fill:
                lot.write(fill)
            notes.append(_('Fleet Number sudah ada, dipakai.'))
        else:
            lot = Lot.create(dict(lot_vals, name=number, product_id=product.id, company_id=company.id,
                                  initial_license_plate=res['license_plate']))
            created.add('lot')

        # 2. Vehicle already there? (a lot creation links a vehicle waiting for it)
        lot.invalidate_recordset(['fleet_vehicle_ids', 'fleet_vehicle_id'])
        vehicle = lot.fleet_vehicle_id
        if not vehicle:
            waiting = Vehicle.search([('lot_id', '=', False), ('asset_number', '=', number),
                                      ('company_id', 'in', [company.id, False])], limit=2)
            if len(waiting) > 1:
                raise UserError(_('Ada beberapa Fleet yang menunggu Fleet Number %s: rapikan duplikatnya dulu.', number))
            if waiting:
                waiting.write({'lot_id': lot.id})
                vehicle = waiting
        if vehicle and 'is_fleet_locked' in vehicle._fields and vehicle.is_fleet_locked:
            raise UserError(_('Fleet %s berstatus nonaktif (read-only).', vehicle.display_name))
        if vehicle:
            notes.append(_('Fleet sudah ada (%s), dipakai.', vehicle.display_name))
            if vehicle.model_id != res['model']:
                notes.append(_('Model di Fleet (%(fleet)s) beda dengan file (%(file)s): Fleet tidak diubah.',
                               fleet=vehicle.model_id.display_name, file=res['model'].display_name))

        # 3. Analytic account, Asset Number = Fleet Number, named after it
        analytic = vehicle.analytic_account_id.sudo() if vehicle else Analytic.browse()
        if analytic:
            notes.append(_('Analytic sudah terhubung (%s).', analytic.display_name))
        else:
            candidates = Analytic.search([('asset_number', '=', number),
                                          ('company_id', 'in', [company.id, False])], limit=2)
            if len(candidates) > 1:
                raise UserError(_('Ada lebih dari satu Analytic dengan Asset Number %s: rapikan dulu.', number))
            analytic = candidates
            if analytic:
                notes.append(_('Analytic %s sudah ada, dipakai.', analytic.display_name))
            else:
                analytic = Analytic.create({
                    'name': number,
                    'asset_number': number,
                    'plan_id': res['plan'].id,
                    'company_id': company.id,
                })
                created.add('analytic')
        other = Vehicle.search([('analytic_account_id', '=', analytic.id), ('id', '!=', vehicle.id)], limit=1)
        if other:
            raise UserError(_('Analytic %(analytic)s sudah dipakai Fleet lain (%(vehicle)s).',
                              analytic=analytic.display_name, vehicle=other.display_name))

        # 4. Vehicle
        if vehicle:
            fill = {}
            if not vehicle.analytic_account_id:
                fill['analytic_account_id'] = analytic.id
            for field, value in (('chassis_number', res['chassis_number']),
                                 ('engine_number', res['engine_number']),
                                 ('color', res['color'].name),
                                 ('model_year', res['year'].name)):
                if value and not vehicle[field]:
                    fill[field] = value
            if res['license_plate'] and not vehicle.initial_license_plate:
                fill['initial_license_plate'] = res['license_plate']
            plate = fill.get('initial_license_plate') or vehicle.initial_license_plate
            if plate and not vehicle.license_plate:
                # as on a vehicle registered from a receipt: plate starts as the initial plate
                fill['license_plate'] = plate
            if fill:
                vehicle.write(fill)
                labels = [vehicle._fields[f].string for f in fill if f != 'analytic_account_id']
                if labels:
                    notes.append(_('Field kosong di Fleet dilengkapi: %s.', ', '.join(labels)))
        else:
            vehicle_vals = {
                'lot_id': lot.id,
                'model_id': res['model'].id,
                'analytic_account_id': analytic.id,
                'company_id': company.id,
                'chassis_number': res['chassis_number'],
                'engine_number': res['engine_number'],
            }
            if res['license_plate']:
                vehicle_vals['initial_license_plate'] = res['license_plate']
            if res['color']:
                vehicle_vals['color'] = res['color'].name
            if res['year']:
                vehicle_vals['model_year'] = res['year'].name
            if res['state']:
                vehicle_vals['state_id'] = res['state'].id
            if res['sub_status']:
                vehicle_vals['fleet_sub_status_id'] = res['sub_status'].id
            vehicle = Vehicle.create(vehicle_vals)
            created.add('vehicle')

        # 5. Stock: qty 1 at its location
        location = res['location']
        quants = Quant.search([('lot_id', '=', lot.id), ('quantity', '>', 0),
                               ('location_id.usage', 'in', ('internal', 'transit'))])
        if quants:
            if quants.location_id == location:
                notes.append(_('Stok sudah ada di %s.', location.complete_name))
            else:
                raise UserError(_('Fleet Number %(number)s sudah punya stok di %(where)s. '
                                  'Pindahkan lewat transfer, bukan lewat import ini.',
                                  number=number, where=', '.join(quants.location_id.mapped('complete_name'))))
        else:
            quants = Quant.with_context(inventory_mode=True).create({
                'product_id': product.id,
                'location_id': location.id,
                'lot_id': lot.id,
                'inventory_quantity': 1,
            })
            quants._apply_inventory()
            created.add('stock')

        if created:
            names = {'lot': _('Fleet Number'), 'analytic': _('Analytic'), 'vehicle': _('Fleet'), 'stock': _('Stok')}
            notes.insert(0, _('Dibuat: %s.', ', '.join(names[k] for k in ('lot', 'analytic', 'vehicle', 'stock')
                                                     if k in created)))
        return notes, created, {'lot': lot, 'vehicle': vehicle, 'analytic': analytic, 'quant': quants}

    # ------------------------------------------------------------------
    # Run
    # ------------------------------------------------------------------
    def _run(self, commit):
        rows = self._read_rows()
        results, seen = [], {}
        for row_no, vals in rows:
            res, errors = self._resolve_row(vals, seen)
            if vals['fleet_number']:
                seen.setdefault(vals['fleet_number'].upper(), row_no)
            results.append({'row': row_no, 'vals': vals, 'res': res, 'errors': errors,
                            'notes': [], 'created': set(), 'records': {}})

        valuation = self._valuation_warnings(results)
        try:
            with self.env.cr.savepoint():
                for result in results:
                    if result['errors']:
                        continue
                    try:
                        with self.env.cr.savepoint():
                            notes, created, records = self._process_row(result['res'])
                    except UserError as exc:
                        result['errors'].append(exc.args[0])
                    except Exception as exc:  # constraint, ValidationError, SQL...
                        _logger.info('Fleet opening import, row %s failed', result['row'], exc_info=True)
                        result['errors'].append(str(exc.args[0] if getattr(exc, 'args', None) else exc))
                    else:
                        result.update(notes=notes, created=created, records=records)
                if not commit or any(r['errors'] for r in results):
                    raise _DryRunRollback()
                sequence_note = self._bump_sequence([r['res']['fleet_number'] for r in results])
        except _DryRunRollback:
            sequence_note = False
            for result in results:
                result['records'] = {}
        self.env.invalidate_all()
        return results, valuation, sequence_note

    def _valuation_warnings(self, results):
        warnings = []
        categories = self.env['product.category']
        for result in results:
            product = result['res'].get('product')
            if product and 'property_valuation' in product.categ_id._fields:
                valuation = product.categ_id.with_company(self.company_id).property_valuation \
                    or getattr(self.company_id, 'inventory_valuation', False)
                if valuation == 'real_time':
                    categories |= product.categ_id
        if categories:
            warnings.append(_(
                'Kategori %s memakai valuasi Perpetual: penambahan stok akan membentuk jurnal persediaan. '
                'Pastikan nilainya tidak dobel dengan register aset (mis. cost produk 0).',
                ', '.join(categories.mapped('display_name'))))
        return warnings

    def _bump_sequence(self, numbers):
        """Move the Fleet Number sequence past the imported numbers it would hand out."""
        company = self.company_id
        sequence = self.env['ir.sequence'].sudo().search(
            [('code', '=', SEQUENCE_CODE), ('company_id', 'in', [company.id, False])],
            order='company_id', limit=1)
        if not sequence:
            return False
        today = fields.Date.context_today(self)
        target = sequence
        date_range = self.env['ir.sequence.date_range']
        if sequence.use_date_range:
            date_range = date_range.sudo().search([('sequence_id', '=', sequence.id),
                                                   ('date_from', '<=', today), ('date_to', '>=', today)], limit=1)
            if not date_range:
                return False
            target = date_range
        prefix, suffix = sequence._get_prefix_suffix(date=today, date_range=date_range.date_from if date_range else None)
        pattern = re.compile(r'^%s(\d+)%s$' % (re.escape(prefix or ''), re.escape(suffix or '')))
        used = [int(m.group(1)) for m in (pattern.match(n or '') for n in numbers) if m]
        if not used:
            return False
        current = target.number_next_actual
        if current > max(used):
            return False
        target.number_next_actual = max(used) + 1
        return _('Sequence Fleet Number dinaikkan: nomor berikutnya %(old)s menjadi %(new)s.',
                 old=current, new=max(used) + 1)

    def _store_results(self, results, done, valuation, sequence_note):
        self.line_ids.sudo().unlink()
        lines = []
        for result in results:
            vals, res = result['vals'], result['res']
            if result['errors']:
                status = 'error'
            elif result['created'] == {'lot', 'analytic', 'vehicle', 'stock'}:
                status = 'new'
            elif result['created']:
                status = 'partial'
            else:
                status = 'exists'
            records = result['records']
            lines.append({
                'wizard_id': self.id,
                'row': result['row'],
                'fleet_number': vals['fleet_number'],
                'product': vals['product'],
                'model': vals['model'],
                'location': vals['location'],
                'license_plate': res.get('license_plate') or vals['license_plate'],
                'status': status,
                'message': '\n'.join(str(m) for m in (result['errors'] or result['notes'])),
                'lot_id': records.get('lot') and records['lot'].id,
                'vehicle_id': records.get('vehicle') and records['vehicle'].id,
                'analytic_id': records.get('analytic') and records['analytic'].id,
            })
        self.env['x.fleet.opening.import.line'].sudo().create(lines)

        errors = sum(1 for r in results if r['errors'])
        items = []
        if done:
            head = _('Import selesai: %s unit diproses.', len(results))
            css = 'alert-success'
            recs = [r['records'] for r in results]
            self.sudo().write({
                'lot_ids': [(6, 0, [r['lot'].id for r in recs if r.get('lot')])],
                'vehicle_ids': [(6, 0, [r['vehicle'].id for r in recs if r.get('vehicle')])],
                'analytic_ids': [(6, 0, [r['analytic'].id for r in recs if r.get('analytic')])],
                'quant_ids': [(6, 0, [q.id for r in recs if r.get('quant') for q in r['quant']])],
            })
            if sequence_note:
                items.append(sequence_note)
        elif errors:
            head = _('%(errors)s dari %(total)s baris error. Tidak ada data yang disimpan: perbaiki filenya, '
                     'lalu upload dan cek lagi.', errors=errors, total=len(results))
            css = 'alert-danger'
        else:
            head = _('Semua %s baris siap diimport. Belum ada data yang disimpan: klik Import.', len(results))
            css = 'alert-info'
        items += valuation
        body = Markup('<div class="alert %s mb-0" role="alert"><strong>%s</strong>%s</div>') % (
            css, head,
            Markup('<ul class="mb-0 mt-2">%s</ul>') % Markup('').join(Markup('<li>%s</li>') % escape(i) for i in items)
            if items else '',
        )
        self.write({'summary': body, 'state': 'done' if done else 'checked'})

    # ------------------------------------------------------------------
    # Template
    # ------------------------------------------------------------------
    def _build_template(self):
        import xlsxwriter
        company = self.company_id
        output = io.BytesIO()
        book = xlsxwriter.Workbook(output, {'in_memory': True})
        f_req = book.add_format({'bold': True, 'font_color': 'white', 'bg_color': '#C0392B', 'border': 1,
                                 'text_wrap': True, 'valign': 'vcenter'})
        f_opt = book.add_format({'bold': True, 'font_color': 'white', 'bg_color': '#2E86C1', 'border': 1,
                                 'text_wrap': True, 'valign': 'vcenter'})
        f_desc = book.add_format({'italic': True, 'font_color': '#7F7F7F', 'text_wrap': True,
                                  'valign': 'top', 'font_size': 9, 'bg_color': '#F2F2F2', 'border': 1})
        f_text = book.add_format({'num_format': '@'})
        f_bold = book.add_format({'bold': True})

        sheet = book.add_worksheet('Unit')
        ref = book.add_worksheet('Referensi')
        guide = book.add_worksheet('Petunjuk')

        refs = {
            'product': self.env['product.product'].search(
                [('is_vehicle', '=', True), ('company_id', 'in', [company.id, False])]).mapped(
                lambda p: p.default_code or p.name),
            'model': self.env['fleet.vehicle.model'].search([]).mapped(
                lambda m: '%s/%s' % (m.brand_id.name, m.name) if m.brand_id else m.name),
            'location': self.env['stock.location'].search(
                [('usage', '=', 'internal'), ('company_id', 'in', [company.id, False])]).mapped('complete_name'),
            'color': self.env['vehicle.color'].search([]).mapped('name'),
            'year': self.env['vehicle.year'].search([]).mapped('name'),
            'state': self.env['fleet.vehicle.state'].search([]).mapped('name'),
            'sub_status': self.env['vehicle.substatus'].search([]).mapped('name'),
            'analytic_plan': self.env['account.analytic.plan'].sudo().search([]).mapped('name'),
        }
        labels = {c[0]: c[1] for c in COLUMNS}
        ref_cols = {}
        for col, (key, values) in enumerate(refs.items()):
            ref.write(0, col, labels[key], f_bold)
            for row, value in enumerate(values, start=1):
                ref.write_string(row, col, value or '')
            ref.set_column(col, col, 28)
            ref_cols[key] = (col, len(values))

        for col, (key, label, required, desc, _a) in enumerate(COLUMNS):
            sheet.write(0, col, label + (' *' if required else ''), f_req if required else f_opt)
            sheet.write(1, col, desc, f_desc)
            sheet.set_column(col, col, 26 if key in ('model', 'location', 'product') else 18, f_text)
            if key in ref_cols and ref_cols[key][1]:
                ref_col, count = ref_cols[key]
                letter = xlsxwriter.utility.xl_col_to_name(ref_col)
                sheet.data_validation(2, col, 1001, col, {
                    'validate': 'list',
                    'source': "=Referensi!$%s$2:$%s$%s" % (letter, letter, count + 1),
                    'error_type': 'warning',
                    'error_title': label,
                    'error_message': _('Nilai tidak ada di daftar Referensi.'),
                })
        sheet.set_row(0, 30)
        sheet.set_row(1, 60)
        sheet.freeze_panes(2, 1)

        lines = [
            _('Import Unit Awal: Fleet Number (SN) + Analytic + Fleet + Stok, sekaligus.'),
            '',
            _('1. Isi sheet "Unit", satu baris per unit, mulai baris 3. Kolom merah wajib.'),
            _('2. Pilihan yang valid ada di sheet "Referensi" (juga sebagai dropdown).'),
            _('3. Upload di Inventory > Operations > Import Unit Awal, klik "Cek File".'),
            _('4. Kalau masih ada baris error, tidak ada yang tersimpan: perbaiki, upload lagi.'),
            _('5. Kalau semua siap, klik "Import". Per baris dibuat (atau dipakai ulang bila sudah ada):'),
            _('   - Fleet Number (Lots/Serial Numbers)'),
            _('   - Analytic Account: nama = Fleet Number, Asset Number = Fleet Number'),
            _('     (berubah otomatis jadi "Plat - Fleet Number" saat STNK di-Running)'),
            _('   - Fleet Vehicle yang terhubung ke Fleet Number dan Analytic'),
            _('   - Stok qty 1 di Lokasi Stok (inventory adjustment langsung di-apply)'),
            _('6. File yang sama aman di-upload ulang: data yang sudah ada tidak dibuat dobel.'),
            '',
            _('Unit yang sudah dijual / disposal tidak perlu diimport.'),
            _('Unit yang sedang disewa: Lokasi Stok = lokasi rental (mis. Customers/Rental).'),
        ]
        guide.set_column(0, 0, 100)
        for row, text in enumerate(lines):
            guide.write(row, 0, text, f_bold if row == 0 else None)
        sheet.activate()
        book.close()
        return output.getvalue()


class FleetOpeningImportLine(models.TransientModel):
    _name = 'x.fleet.opening.import.line'
    _description = 'Import Unit Awal: hasil per baris'
    _order = 'row'

    wizard_id = fields.Many2one('x.fleet.opening.import', required=True, ondelete='cascade')
    row = fields.Integer(string='Baris Excel')
    fleet_number = fields.Char()
    product = fields.Char(string='Produk')
    model = fields.Char()
    location = fields.Char(string='Lokasi')
    license_plate = fields.Char(string='Plat')
    status = fields.Selection([
        ('new', 'Baru'),
        ('partial', 'Sebagian sudah ada'),
        ('exists', 'Sudah ada semua'),
        ('error', 'Error'),
    ])
    message = fields.Text(string='Keterangan')
    lot_id = fields.Many2one('stock.lot', string='SN')
    vehicle_id = fields.Many2one('fleet.vehicle', string='Fleet')
    analytic_id = fields.Many2one('account.analytic.account', string='Analytic',
                                  groups='analytic.group_analytic_accounting')
