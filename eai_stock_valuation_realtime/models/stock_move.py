"""Mesin valuasi real-time per stock move (gaya Odoo 17) untuk kategori bertanda.

Prinsip:
1. GL mengikuti nilai stock move. Odoo 19 menghitung `stock.move.value`; addon ini tidak
   menghitung ulang, hanya menjurnal nilai tersebut. Setiap kali nilai berubah (receipt
   dinilai ulang karena bill datang dengan harga lain, landed cost, koreksi qty), yang
   dijurnal adalah selisihnya (delta) terhadap nilai yang sudah dijurnal
   (`eai_rt_posted_value`). Jurnal lama tidak pernah diedit.
2. Satu mesin, banyak pola: akun lawan ditentukan dari jenis move (asal -> tujuan).
3. Kategori tidak bertanda tidak disentuh sama sekali.
"""
from odoo import api, fields, models
from odoo.exceptions import UserError

# Peran baris jurnal, dipakai laporan rekonsiliasi (lihat account.move.line.eai_rt_role).
ROLE_BY_KEY = {
    'stock': 'stock',
    'input': 'input',
    'output': 'output',
    'claim': 'claim',
}


class StockMove(models.Model):
    _inherit = 'stock.move'

    eai_rt_posted_value = fields.Monetary(
        'Nilai sudah dijurnal (real-time)', currency_field='company_currency_id',
        copy=False, readonly=True,
        help="Nilai move yang sudah dijurnal oleh valuasi real-time. Selisih terhadap Value "
             "akan dijurnal sebagai koreksi.")
    eai_rt_claim_value = fields.Monetary(
        'Nilai Klaim Retur', currency_field='company_currency_id', copy=False, readonly=True,
        help="Untuk retur ke vendor: nilai klaim (qty x harga bill asal) yang didebit ke Piutang Klaim.")
    eai_rt_account_move_ids = fields.One2many(
        'account.move', 'eai_rt_stock_move_id', string='Jurnal Valuasi Real-time', readonly=True)
    eai_rt_account_move_count = fields.Integer(compute='_compute_eai_rt_account_move_count')

    @api.depends('eai_rt_account_move_ids')
    def _compute_eai_rt_account_move_count(self):
        for move in self:
            move.eai_rt_account_move_count = len(move.eai_rt_account_move_ids)

    # ------------------------------------------------------------------
    # Penentu: apakah move ini diproses addon
    # ------------------------------------------------------------------
    def _eai_rt_is_enabled(self):
        self.ensure_one()
        product = self.product_id.with_company(self.company_id)
        return bool(
            product.is_storable
            and product.categ_id.eai_rt_enabled
            and product.valuation == 'real_time'
        )

    def _should_create_account_move(self):
        # Kategori bertanda dijurnal oleh mesin addon; jangan buat jurnal standar
        # (reklas lokasi) agar tidak dobel.
        if self._eai_rt_is_enabled():
            return False
        return super()._should_create_account_move()

    @api.model
    def _eai_rt_mark_as_posted(self, products):
        """Tandai nilai move done yang sudah ada sebagai 'sudah dijurnal' (titik awal)."""
        if not products:
            return
        self.env.flush_all()
        self.env.cr.execute("""
            UPDATE stock_move
               SET eai_rt_posted_value = CASE WHEN is_out THEN -COALESCE(value, 0) ELSE COALESCE(value, 0) END
             WHERE product_id = ANY(%s) AND state = 'done'
               AND NOT EXISTS (SELECT 1 FROM account_move am WHERE am.eai_rt_stock_move_id = stock_move.id)
        """, [products.ids])
        self.invalidate_model(['eai_rt_posted_value'])

    # ------------------------------------------------------------------
    # Pemicu: setiap perubahan `value`
    # ------------------------------------------------------------------
    def write(self, vals):
        res = super().write(vals)
        if 'value' in vals and not self.env.context.get('eai_rt_skip_sync') \
                and not self.env.context.get('eai_rt_defer_sync'):
            self._eai_rt_sync_valuation()
        return res

    def _action_done(self, cancel_backorder=False):
        moves = super()._action_done(cancel_backorder=cancel_backorder)
        # Jaring pengaman: move bernilai yang nilainya tidak berubah lewat write
        # (mis. nilai sudah terisi sebelum done) tetap dijurnal.
        moves._eai_rt_sync_valuation()
        return moves

    def _set_value(self, correction_quantity=None):
        """Odoo 19 menilai ulang barang masuk lewat `_set_value` (bill, landed cost).

        Rata-rata Odoo 19 dihitung ulang dari semua move, tetapi nilai barang yang sudah keluar
        tidak dikoreksi. Karena itu kenaikan/penurunan nilai receipt tidak seluruhnya menjadi
        nilai persediaan: hanya perubahan nilai valuasi produk yang masuk ke Persediaan, sisanya
        (porsi barang yang sudah keluar) ke akun selisih harga. Jurnal dibuat setelah standar
        selesai menghitung ulang harga rata-rata.
        """
        if self.env.context.get('eai_rt_defer_sync'):
            return super()._set_value(correction_quantity=correction_quantity)
        # Hanya koreksi nilai receipt yang sudah pernah dijurnal; penjurnalan pertama tetap utuh.
        tracked = self.filtered(lambda m: m.state == 'done' and m.is_in and m.eai_rt_account_move_ids
                                and m._eai_rt_is_enabled())
        before = {}
        for move in tracked:
            key = (move.company_id, move.product_id)
            if key not in before:
                before[key] = move.product_id.with_company(move.company_id).total_value
        res = super(StockMove, self.with_context(eai_rt_defer_sync=True))._set_value(
            correction_quantity=correction_quantity)
        stock_ratio = {}
        if before:
            self.env.flush_all()
            self.env['product.product'].invalidate_model(['total_value', 'avg_cost', 'standard_price'])
            deltas = {}
            for move in tracked:
                key = (move.company_id, move.product_id)
                deltas[key] = deltas.get(key, 0.0) + move._eai_rt_signed_value() - move.eai_rt_posted_value
            for (company, product), total_delta in deltas.items():
                if company.currency_id.is_zero(total_delta):
                    continue
                after = product.with_company(company).total_value
                stock_ratio[(company.id, product.id)] = (after - before[(company, product)]) / total_delta
        self.with_context(eai_rt_stock_ratio=stock_ratio)._eai_rt_sync_valuation()
        return res

    def _eai_rt_sync_valuation(self):
        for move in self:
            if move.state != 'done' or not move._eai_rt_is_enabled():
                continue
            move = move.with_company(move.company_id)
            kind = move._eai_rt_kind()
            if not kind:
                continue
            signed_value = move._eai_rt_signed_value()
            delta = signed_value - move.eai_rt_posted_value
            if move.company_currency_id.is_zero(delta):
                continue
            initial = not move.eai_rt_account_move_ids
            lines = move._eai_rt_prepare_lines(kind, delta, initial)
            if not lines:
                continue
            move._eai_rt_create_entry(lines, initial)
            move.sudo().with_context(eai_rt_skip_sync=True).write({'eai_rt_posted_value': signed_value})

    def _eai_rt_signed_value(self):
        """Nilai move bertanda: positif untuk barang masuk, negatif untuk barang keluar.

        Odoo 19 menyimpan `value` barang keluar sebagai angka positif; mesin addon bekerja
        dengan nilai bertanda (seperti stock valuation layer di v17).
        """
        self.ensure_one()
        return -self.value if (self.is_out and not self.is_dropship) else self.value

    def _eai_rt_kind(self):
        """Jenis move menurut asal -> tujuan (seperti `_account_entry_move` v17)."""
        self.ensure_one()
        if self.is_dropship:
            return 'dropship'
        if self.is_in:
            usage = self.location_id.usage
            if usage == 'customer':
                return 'sale_return'
            if usage == 'inventory':
                return 'inventory_in'
            if usage in ('supplier', 'transit'):
                return 'receipt'
            return 'other_in'
        if self.is_out:
            usage = self.location_dest_id.usage
            if usage == 'supplier':
                return 'purchase_return'
            if usage == 'customer':
                return 'delivery'
            # Scrap dikenali dari dokumen scrap pada move (lokasi scrap bisa bertipe inventory).
            if self.scrap_id:
                return 'scrap'
            if usage == 'inventory':
                return 'inventory_out'
            return 'other_out'
        return False

    # ------------------------------------------------------------------
    # Penyusunan baris jurnal
    # ------------------------------------------------------------------
    def _eai_rt_accounts(self):
        self.ensure_one()
        return self.product_id.categ_id._eai_rt_get_accounts(self.company_id)

    def _eai_rt_prepare_lines(self, kind, delta, initial):
        """Kembalikan list (key_akun, account, balance). Balance positif = debit.

        `delta` adalah perubahan nilai bertanda (`_eai_rt_signed_value`): positif untuk
        barang masuk, negatif untuk barang keluar. Baris Stock selalu bernilai `delta`.
        """
        self.ensure_one()
        categ = self.product_id.categ_id
        accounts = self._eai_rt_accounts()
        currency = self.company_currency_id

        if kind == 'dropship':
            categ._eai_rt_require(accounts, ['input', 'output', 'journal'])
            return [('output', accounts['output'], delta), ('input', accounts['input'], -delta)]

        categ._eai_rt_require(accounts, ['stock', 'journal'])
        lines = [('stock', accounts['stock'], delta)]

        # Landed cost: seperti standar Odoo 19, hanya porsi qty yang masih di stok yang
        # dikapitalisasi (Dr Stock / Cr akun biaya landed cost). Porsi barang yang sudah
        # keluar tetap menjadi beban di akun biaya landed cost.
        extra = (self.env.context.get('eai_rt_extra_counterparts') or {}).get(self.id)
        if extra:
            capitalized = currency.round(sum(amount for _account_id, amount in extra))
            lines = [('stock', accounts['stock'], capitalized)]
            for account_id, amount in extra:
                lines.append(('other', self.env['account.account'].browse(account_id), -amount))
            return lines

        if kind == 'purchase_return':
            if initial:
                categ._eai_rt_require(accounts, ['claim', 'price_diff'])
                claim = currency.round(self._eai_rt_compute_claim_value())
                diff = currency.round(-delta - claim)
                lines.append(('claim' if accounts['claim_is_separate'] else 'input', accounts['claim'], claim))
                if not currency.is_zero(diff):
                    lines.append(('price_diff', accounts['price_diff'], diff))
                self.sudo().with_context(eai_rt_skip_sync=True).write({'eai_rt_claim_value': claim})
                return lines
            # Nilai retur berubah setelah dijurnal (koreksi qty): klaim tetap, selisih ke akun selisih harga retur.
            categ._eai_rt_require(accounts, ['price_diff'])
            lines.append(('price_diff', accounts['price_diff'], -delta))
            return lines

        key, counterpart = self._eai_rt_counterpart(kind, accounts)
        ratio = (self.env.context.get('eai_rt_stock_ratio') or {}).get((self.company_id.id, self.product_id.id))
        if self.is_in and not initial and ratio is not None \
                and not currency.is_zero(delta - currency.round(delta * ratio)):
            # Sebagian perubahan nilai milik barang yang sudah keluar: ke akun selisih harga.
            categ._eai_rt_require(accounts, ['price_diff'])
            stock_part = currency.round(delta * ratio)
            lines = [('stock', accounts['stock'], stock_part),
                     ('price_diff', accounts['price_diff'], delta - stock_part)]
        lines.append((key, counterpart, -delta))
        if self.is_out:
            lines += self._eai_rt_rounding_lines(accounts, delta)
        return lines

    def _eai_rt_rounding_lines(self, accounts, delta):
        """Bersihkan sisa pembulatan rata-rata saat stok produk habis.

        AVCO menilai barang keluar = qty x rata-rata (dibulatkan), sehingga GL persediaan
        produk bisa menyisakan beberapa sen ketika stok sudah nol. Bila sisanya kecil
        (<= 100 x pembulatan mata uang), sisa itu dipindahkan ke Akun Selisih Harga
        pada jurnal move terakhir ini. Selisih yang lebih besar tidak disentuh supaya
        tetap terlihat sebagai indikasi masalah.
        """
        self.ensure_one()
        currency = self.company_currency_id
        product = self.product_id.with_company(self.company_id)
        if not accounts.get('price_diff') or not currency.is_zero(product.qty_available):
            return []
        aml = self.env['account.move.line'].sudo().search_fetch([
            ('company_id', '=', self.company_id.id),
            ('account_id', '=', accounts['stock'].id),
            ('product_id', '=', product.id),
            ('parent_state', '!=', 'cancel'),
        ], ['balance'])
        residual = currency.round(sum(aml.mapped('balance')) + delta)
        if currency.is_zero(residual) or abs(residual) > currency.rounding * 100:
            return []
        return [('stock', accounts['stock'], -residual), ('price_diff', accounts['price_diff'], residual)]

    def _eai_rt_counterpart(self, kind, accounts):
        """Akun lawan Stock untuk move biasa. Akun valuasi pada lokasi (fitur standar
        `stock.location.valuation_account_id`) dihormati untuk lokasi non-partner."""
        self.ensure_one()
        categ = self.product_id.categ_id
        other_location = self.location_id if self.is_in else self.location_dest_id
        if kind in ('inventory_in', 'inventory_out', 'scrap', 'other_in', 'other_out') \
                and other_location.valuation_account_id:
            return 'other', other_location.valuation_account_id
        mapping = {
            'receipt': 'input',
            'other_in': 'input',
            'sale_return': 'output',
            'delivery': 'output',
            'other_out': 'output',
            'inventory_in': 'inventory_diff',
            'inventory_out': 'inventory_diff',
            'scrap': 'scrap',
        }
        key = mapping[kind]
        categ._eai_rt_require(accounts, [key])
        return (key if key in ROLE_BY_KEY else 'other'), accounts[key]

    def _eai_rt_compute_claim_value(self):
        """Nilai klaim retur ke vendor = qty x harga satuan penerimaan asal (harga bill).

        Urutan sumber: nilai receipt asal (sudah memakai harga bill bila bill diposting),
        lalu rata-rata harga bill pada PO line, lalu harga PO, lalu nilai move itu sendiri.
        """
        self.ensure_one()
        qty = self._get_valued_qty()
        origin = self.origin_returned_move_id
        if origin and origin.is_in:
            origin_qty = origin._get_valued_qty()
            if origin_qty:
                return abs(origin.value) / origin_qty * qty
        pol = self.purchase_line_id
        if pol:
            bill_qty = bill_value = 0.0
            for aml in pol.invoice_lines.filtered(
                    lambda l: l.parent_state == 'posted' and l.move_type == 'in_invoice'):
                bill_qty += aml.product_uom_id._compute_quantity(aml.quantity, self.product_id.uom_id)
                bill_value += abs(aml.balance)
            if bill_qty:
                return bill_value / bill_qty * qty
            return pol._get_stock_move_price_unit() * qty
        return abs(self.value)

    # ------------------------------------------------------------------
    # Pembuatan jurnal
    # ------------------------------------------------------------------
    def _eai_rt_entry_date(self, initial, journal):
        self.ensure_one()
        forced = self.env.context.get('force_period_date')
        if forced:
            date = fields.Date.to_date(forced)
        elif initial:
            date = fields.Date.context_today(self, self.date)
        else:
            # Koreksi nilai dicatat pada periode saat koreksi terjadi (seperti v17).
            date = fields.Date.context_today(self)
        lock_date = self.company_id._get_user_fiscal_lock_date(journal)
        if lock_date and date <= lock_date:
            date = fields.Date.add(lock_date, days=1)
        return date

    def _eai_rt_origin_ref(self):
        self.ensure_one()
        return (
            self.purchase_line_id.order_id.name
            or self.sale_line_id.order_id.name
            or self.origin_returned_move_id.purchase_line_id.order_id.name
            or self.origin_returned_move_id.sale_line_id.order_id.name
            or self.origin
            or self.picking_id.name
            or self.reference
        )

    def _eai_rt_warehouse(self):
        self.ensure_one()
        location = self.location_dest_id if self.is_in else self.location_id
        return location.warehouse_id or self.warehouse_id or self.picking_type_id.warehouse_id

    def _eai_rt_create_entry(self, lines, initial):
        self.ensure_one()
        accounts = self._eai_rt_accounts()
        journal = accounts['journal']
        warehouse = self._eai_rt_warehouse()
        analytic = warehouse.eai_rt_analytic_account_id
        partner_id = self._get_partner_id_for_valuation_lines()
        # Jurnal koreksi nilai tidak memindahkan barang: qty 0, supaya qty di laporan saldo
        # interim tidak terhitung dua kali.
        qty = self._get_valued_qty() if initial else 0.0
        label = f"{self.reference} - {self.product_id.display_name}"
        if not initial:
            label = self.env._("Koreksi nilai: %(label)s", label=label)
        origin_ref = self._eai_rt_origin_ref()

        line_vals = []
        for key, account, balance in lines:
            if self.company_currency_id.is_zero(balance):
                continue
            line_vals.append({
                'account_id': account.id,
                'name': label,
                'balance': balance,
                'product_id': self.product_id.id,
                'quantity': qty,
                'product_uom_id': self.product_id.uom_id.id,
                'partner_id': partner_id,
                'analytic_distribution': {str(analytic.id): 100} if analytic else False,
                'eai_rt_role': ROLE_BY_KEY.get(key, 'other'),
                'eai_rt_origin_ref': origin_ref,
                'eai_rt_warehouse_id': warehouse.id,
            })
        if not line_vals:
            return self.env['account.move']

        entry = self.env['account.move'].sudo().create({
            'move_type': 'entry',
            'journal_id': journal.id,
            'date': self._eai_rt_entry_date(initial, journal),
            'ref': label if initial else self.env._("%(ref)s (koreksi)", ref=self.reference),
            'partner_id': partner_id,
            'company_id': self.company_id.id,
            'eai_rt_stock_move_id': self.id,
            'line_ids': [fields.Command.create(vals) for vals in line_vals],
        })
        if not self.account_move_id:
            # Tautan standar: smart button jurnal di transfer / move.
            self.sudo().with_context(eai_rt_skip_sync=True).write({'account_move_id': entry.id})
        if self.company_id.eai_rt_auto_post:
            entry._post()
        return entry

    # ------------------------------------------------------------------
    # Credit note vendor yang menutup klaim retur tidak boleh menurunkan nilai receipt
    # (barangnya sudah keluar lewat retur). Lihat purchase_stock `_get_value_from_account_move`.
    # ------------------------------------------------------------------
    def _get_quantity_from_bill(self, aml, quantity):
        if aml.eai_rt_is_claim:
            return 0.0
        return super()._get_quantity_from_bill(aml, quantity)

    def _get_value_from_bill(self, aml):
        if aml.eai_rt_is_claim:
            return 0.0
        return super()._get_value_from_bill(aml)

    # ------------------------------------------------------------------
    # Navigasi
    # ------------------------------------------------------------------
    def action_eai_rt_view_entries(self):
        entries = self.eai_rt_account_move_ids
        action = self.env['ir.actions.act_window']._for_xml_id('account.action_move_journal_line')
        action['domain'] = [('id', 'in', entries.ids)]
        action['context'] = {'create': False}
        if len(entries) == 1:
            action.update({'view_mode': 'form', 'views': [(False, 'form')], 'res_id': entries.id})
        return action


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    eai_rt_account_move_count = fields.Integer(compute='_compute_eai_rt_account_move_count')

    def _compute_eai_rt_account_move_count(self):
        for picking in self:
            picking.eai_rt_account_move_count = len(picking.move_ids.eai_rt_account_move_ids)

    def action_eai_rt_view_entries(self):
        return self.move_ids.action_eai_rt_view_entries()
