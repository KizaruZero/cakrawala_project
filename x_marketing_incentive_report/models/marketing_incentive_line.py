# -*- coding: utf-8 -*-
from collections import defaultdict

from odoo import _, api, fields, models
from odoo.exceptions import AccessError


class MarketingIncentiveLine(models.Model):
    """Satu baris = satu unit Rental Order Line yang sudah Live.

    Data diambil (dibaca) dari Rental Order Line, RPC dan Fleet lalu
    disimpan di tabel ini. Modul ini tidak menulis apa pun ke RPC,
    Rental Order maupun Fleet.
    """
    _name = 'x.marketing.incentive.line'
    _description = 'Insentif Marketing per Unit'
    _order = 'live_date desc, user_id, id'
    _rec_name = 'display_label'

    company_id = fields.Many2one(
        'res.company', string='Company', required=True,
        default=lambda self: self.env.company, index=True,
    )
    currency_id = fields.Many2one(related='company_id.currency_id', store=True)

    # Sumber
    sale_line_id = fields.Many2one(
        'sale.order.line', string='Rental Order Line', required=True,
        ondelete='cascade', index=True, readonly=True,
    )
    sale_order_id = fields.Many2one(
        'sale.order', string='Rental Order', index=True, readonly=True,
    )
    rpc_document_id = fields.Many2one(
        'rpc.document', string='RPC', index=True, readonly=True,
    )
    rpc_name = fields.Char(string='No. RPC', readonly=True)
    user_id = fields.Many2one(
        'res.users', string='Sales Person', index=True, readonly=True,
    )
    partner_id = fields.Many2one('res.partner', string='Client', readonly=True)
    kriteria = fields.Char(string='Kriteria', readonly=True,
                           help='Jenis Transaksi di RPC.')

    # Unit
    fleet_vehicle_id = fields.Many2one('fleet.vehicle', string='Unit', readonly=True)
    license_plate = fields.Char(string='NOPOL', readonly=True)
    vehicle_name = fields.Char(string='Merk & Tipe Kend', readonly=True)
    model_year = fields.Char(string='Tahun Kend', readonly=True)
    category = fields.Selection(
        [('ice', 'ICE'), ('ev', 'EV')], string='Kategori', readonly=True,
        help='EV bila Fuel Type unit di Fleet = Electric; selain itu ICE '
             '(termasuk hybrid).',
    )

    # Angka dari RPC
    price_side = fields.Selection(
        [('upper', 'Batas Atas'), ('lower', 'Batas Bawah')],
        string='Harga Sewa Final', readonly=True,
    )
    otr_amount = fields.Monetary(string='OTR/BV', readonly=True,
                                 help='OTR Final di RPC.')
    rental_price = fields.Monetary(string='Sewa/bln', readonly=True,
                                   help='Harga Sewa/Bulan Final di RPC.')
    marketing_cost = fields.Monetary(
        string='Komisi External', readonly=True,
        help='Total Biaya Marketing dan Komisi di RPC dibagi '
             '(Masa Sewa x Jumlah Unit), per unit per bulan.',
    )
    ruu_net = fields.Float(string='RUU Net', digits=(16, 6), readonly=True,
                           help='RUU Netto di RPC sesuai Harga Sewa Final.')
    tenor = fields.Integer(string='Tenor (Bln)', readonly=True)
    live_date = fields.Date(string='Tgl Live', index=True, readonly=True,
                            help='Actual Delivery di Rental Order Line.')
    incentive_permille = fields.Float(
        string='Insentif (‰)', digits=(16, 3), readonly=True,
        help='Faktor Pengali RPC dalam permil.',
    )
    rpc_unit_incentive = fields.Monetary(
        string='Insentif RPC / Unit', readonly=True,
        help='Jumlah Insentif RPC dibagi Jumlah Unit, sebelum potongan EV.',
    )
    ev_ratio = fields.Float(string='Rasio Kategori', digits=(16, 2), readonly=True)
    incentive_amount = fields.Monetary(string='Insentif (Rp)', readonly=True)
    rpc_eligible = fields.Boolean(string='Memenuhi Syarat RPC', readonly=True)
    note = fields.Char(string='Catatan', readonly=True)
    generated_at = fields.Datetime(string='Diambil Pada', readonly=True)
    generated_by_id = fields.Many2one('res.users', string='Diambil Oleh', readonly=True)

    display_label = fields.Char(compute='_compute_display_label')

    _sale_line_unique = models.Constraint(
        'UNIQUE(sale_line_id)',
        'Satu Rental Order Line hanya boleh punya satu baris insentif.',
    )

    @api.depends('license_plate', 'sale_order_id')
    def _compute_display_label(self):
        for rec in self:
            rec.display_label = ' - '.join(filter(None, (
                rec.sale_order_id.name, rec.license_plate,
            ))) or _('Insentif')

    # ------------------------------------------------------------------
    # Pengambilan data
    # ------------------------------------------------------------------
    @api.model
    def _ev_ratio(self):
        raw = self.env['ir.config_parameter'].sudo().get_param(
            'x_marketing_incentive_report.ev_ratio', '0.8')
        try:
            return float(raw)
        except (TypeError, ValueError):
            return 0.8

    @api.model
    def _candidate_sale_lines(self, date_from, date_to):
        domain = [
            ('actual_delivery_date', '>=', date_from),
            ('actual_delivery_date', '<=', date_to),
            ('display_type', '=', False),
            ('order_id.rpc_document_ids', '!=', False),
            ('product_id.is_vehicle', '=', True),
        ]
        return self.env['sale.order.line'].sudo().search(domain, order='order_id, id')

    @api.model
    def _rpc_by_line(self, order):
        """Petakan setiap baris unit di Rental Order ke dokumen RPC-nya.

        Rental Order dari satu RPC: semua baris memakai RPC itu.
        Rental Order gabungan beberapa RPC: dicocokkan lewat produk di
        Input Line (rpc_document_id per produk, sebanyak quantity-nya),
        berurutan sesuai id baris.
        """
        docs = order.rpc_document_ids
        unit_lines = order.order_line.filtered(
            lambda l: not l.display_type and l.product_id.is_vehicle
        ).sorted('id')
        if len(docs) <= 1:
            return {line.id: docs[:1] for line in unit_lines}

        queue = defaultdict(list)
        if 'sale.order.input.line' in self.env:
            inputs = self.env['sale.order.input.line'].sudo().search(
                [('order_id', '=', order.id)], order='id')
            for inp in inputs:
                if inp.rpc_document_id and inp.product_id:
                    qty = max(int(round(inp.quantity or 0)), 1)
                    queue[inp.product_id.id].extend([inp.rpc_document_id] * qty)

        fallback = order.rpc_document_id or docs[:1]
        result = {}
        for line in unit_lines:
            pending = queue.get(line.product_id.id)
            result[line.id] = pending.pop(0) if pending else fallback
        return result

    @api.model
    def _find_vehicle(self, line):
        """Unit yang dikirim: lot pada pengiriman keluar yang sudah done,
        cadangan lewat analytic account baris."""
        Vehicle = self.env['fleet.vehicle'].sudo()
        move_line = self.env['stock.move.line'].sudo().search([
            ('move_id.sale_line_id', '=', line.id),
            ('state', '=', 'done'),
            ('lot_id', '!=', False),
            ('location_dest_id.usage', '=', 'customer'),
        ], order='date desc, id desc', limit=1)
        lot = move_line.lot_id
        if lot and 'fleet_vehicle_id' in lot._fields and lot.fleet_vehicle_id:
            return lot.fleet_vehicle_id
        if lot:
            vehicle = Vehicle.search([('lot_id', '=', lot.id)], limit=1) \
                if 'lot_id' in Vehicle._fields else Vehicle
            if vehicle:
                return vehicle
        if line.analytic_distribution and 'analytic_account_id' in Vehicle._fields:
            account_ids = []
            for key in line.analytic_distribution:
                account_ids += [int(k) for k in str(key).split(',') if k.isdigit()]
            if account_ids:
                vehicle = Vehicle.search(
                    [('analytic_account_id', 'in', account_ids)], limit=1)
                if vehicle:
                    return vehicle
        return Vehicle

    @api.model
    def _prepare_values(self, line, rpc, line_count=0):
        order = line.order_id
        currency = order.currency_id or self.env.company.currency_id
        rpc = rpc.sudo()
        vehicle = self._find_vehicle(line)
        notes = []

        side = rpc.final_rental_price_type or 'upper'
        if side == 'lower':
            factor = rpc.insentif_faktor_pengali_batas_bawah
            rpc_total = rpc.insentif_jumlah_batas_bawah
            ruu = rpc.ruu_netto_batas_bawah
            price = rpc.final_rental_price or rpc.sewa_per_bulan_batas_bawah
        else:
            factor = rpc.insentif_faktor_pengali_batas_atas
            rpc_total = rpc.insentif_jumlah_batas_atas
            ruu = rpc.ruu_netto
            price = rpc.final_rental_price or rpc.sewa_per_bulan_batas_atas

        units = rpc.jumlah_unit or 1
        months = rpc.masa_sewa or 0
        marketing_cost = (
            rpc.total_biaya_marketing / (months * units)
            if months and units else 0.0
        )

        eligible = rpc.insentif_check_summary == 'yes'
        per_unit = rpc_total / units if units else 0.0
        if not eligible:
            failed = []
            if rpc.insentif_check_type_klien != 'yes':
                failed.append(_('Type Klien'))
            if rpc.insentif_check_jenis_transaksi != 'yes':
                failed.append(_('Jenis Transaksi'))
            if rpc.insentif_check_masa_sewa != 'yes':
                failed.append(_('Masa Sewa'))
            notes.append(_('Tidak memenuhi syarat insentif RPC: %s',
                           ', '.join(failed) or _('Summary NO')))
            per_unit = 0.0
        elif not factor:
            notes.append(_('Faktor pengali RPC tidak ditemukan untuk kombinasi ini.'))

        if vehicle:
            category = 'ev' if vehicle.fuel_type == 'electric' else 'ice'
            if not vehicle.fuel_type:
                notes.append(_('Fuel Type unit kosong, dianggap ICE.'))
        else:
            category = 'ice'
            per_unit = 0.0
            notes.append(_('Unit yang dikirim tidak ditemukan (tidak ada lot di '
                           'pengiriman), insentif 0. Cek Rental Order Line ini.'))

        if line_count > units:
            notes.append(_('Rental Order punya %(lines)s baris unit untuk RPC ini, '
                           'sedangkan Jumlah Unit RPC %(units)s. Cek baris ganda.',
                           lines=line_count, units=units))

        ratio = self._ev_ratio() if category == 'ev' else 1.0
        model_year = vehicle.model_year if vehicle else False

        return {
            'company_id': order.company_id.id or self.env.company.id,
            'sale_line_id': line.id,
            'sale_order_id': order.id,
            'rpc_document_id': rpc.id,
            'rpc_name': rpc.name,
            'user_id': order.user_id.id,
            'partner_id': order.partner_id.id,
            'kriteria': rpc.jenis_transaksi_id.name or False,
            'fleet_vehicle_id': vehicle.id or False,
            'license_plate': vehicle.license_plate if vehicle else False,
            'vehicle_name': (
                vehicle.model_id.display_name if vehicle and vehicle.model_id
                else line.product_id.display_name
            ),
            'model_year': str(model_year) if model_year else False,
            'category': category,
            'price_side': side,
            'otr_amount': rpc.otr_final,
            'rental_price': price,
            'marketing_cost': currency.round(marketing_cost),
            'ruu_net': ruu,
            'tenor': months,
            'live_date': line.actual_delivery_date,
            'incentive_permille': factor * 100.0,
            'rpc_unit_incentive': currency.round(per_unit),
            'ev_ratio': ratio,
            'incentive_amount': currency.round(per_unit * ratio),
            'rpc_eligible': eligible,
            'note': ' '.join(notes) or False,
            'generated_at': fields.Datetime.now(),
            'generated_by_id': self.env.user.id,
        }

    @api.model
    def generate_for_period(self, date_from, date_to, regenerate=False):
        """Ambil data periode. Baris yang sudah ada tidak diubah kecuali
        regenerate=True (khusus Manager). Mengembalikan jumlah baris
        baru dan yang dihitung ulang."""
        if regenerate and not self.env.user.has_group(
                'x_marketing_incentive_report.group_marketing_incentive_manager'):
            raise AccessError(_('Hitung ulang hanya untuk Insentif Marketing: Manager.'))

        lines = self._candidate_sale_lines(date_from, date_to)
        existing = self.sudo().search([('sale_line_id', 'in', lines.ids)])
        existing_by_line = {rec.sale_line_id.id: rec for rec in existing}

        created = updated = 0
        to_create = []
        rpc_maps = {}
        for line in lines:
            order = line.order_id
            if order.id not in rpc_maps:
                rpc_maps[order.id] = self._rpc_by_line(order)
            rpc = rpc_maps[order.id].get(line.id)
            if not rpc:
                continue
            current = existing_by_line.get(line.id)
            if current and not regenerate:
                continue
            line_count = list(rpc_maps[order.id].values()).count(rpc)
            values = self._prepare_values(line, rpc, line_count)
            if current:
                current.sudo().write(values)
                updated += 1
            else:
                to_create.append(values)
        if to_create:
            self.sudo().create(to_create)
            created = len(to_create)
        return {'created': created, 'updated': updated, 'found': len(lines)}

    def action_recompute(self):
        if not self.env.user.has_group(
                'x_marketing_incentive_report.group_marketing_incentive_manager'):
            raise AccessError(_('Hitung ulang hanya untuk Insentif Marketing: Manager.'))
        for rec in self:
            line = rec.sale_line_id
            mapping = self._rpc_by_line(line.order_id)
            rpc = mapping.get(line.id) or rec.rpc_document_id
            if rpc:
                count = list(mapping.values()).count(rpc)
                rec.sudo().write(self._prepare_values(line, rpc, count))
        return True
