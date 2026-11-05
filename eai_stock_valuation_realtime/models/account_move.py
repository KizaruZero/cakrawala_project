from odoo import fields, models
from odoo.exceptions import UserError


class AccountMove(models.Model):
    _inherit = 'account.move'

    eai_rt_stock_move_id = fields.Many2one(
        'stock.move', string='Stock Move (valuasi RT)', copy=False, readonly=True,
        index='btree_not_null', ondelete='restrict')

    # ------------------------------------------------------------------
    # Proteksi jurnal valuasi otomatis
    # ------------------------------------------------------------------
    def _eai_rt_check_protected(self):
        if self.env.context.get('eai_rt_internal'):
            return
        if self.filtered('eai_rt_stock_move_id'):
            raise UserError(self.env._(
                "Jurnal ini dibuat otomatis oleh valuasi real-time dari pergerakan stok. "
                "Koreksi dilakukan lewat dokumen stok (retur, penyesuaian, atau revaluasi), "
                "bukan dengan mengubah jurnalnya."))

    def button_draft(self):
        self._eai_rt_check_protected()
        return super().button_draft()

    def button_cancel(self):
        self._eai_rt_check_protected()
        return super().button_cancel()

    def unlink(self):
        self._eai_rt_check_protected()
        return super().unlink()

    def _reverse_moves(self, default_values_list=None, cancel=False):
        self._eai_rt_check_protected()
        return super()._reverse_moves(default_values_list=default_values_list, cancel=cancel)

    # ------------------------------------------------------------------
    # Posting bill / credit note / invoice
    # ------------------------------------------------------------------
    def _post(self, soft=True):
        if not self.env.context.get('move_reverse_cancel'):
            claim_vals = []
            for move in self.filtered(lambda m: m.state == 'draft' and m.is_invoice(include_receipts=True)):
                move = move.with_company(move.company_id)
                move._eai_rt_prepare_invoice_lines()
                if move.move_type == 'in_refund':
                    claim_vals += move._eai_rt_claim_difference_lines_vals()
            if claim_vals:
                self.env['account.move.line'].create(claim_vals)
        return super()._post(soft)

    def _eai_rt_prepare_invoice_lines(self):
        """Validasi konfigurasi dan tetapkan akun final baris produk kategori bertanda."""
        self.ensure_one()
        for line in self.invoice_line_ids:
            if line.display_type != 'product' or not line.product_id or not line._eai_rt_enabled():
                continue
            if not line._eligible_for_stock_account():
                continue
            categ = line.product_id.categ_id
            accounts = line._eai_rt_accounts()
            vals = {}
            if self.is_purchase_document(include_receipts=True):
                pol = line.purchase_line_id
                vals['eai_rt_origin_ref'] = pol.order_id.name or self.name
                vals['eai_rt_warehouse_id'] = pol.order_id.picking_type_id.warehouse_id.id
                if self.move_type == 'in_refund':
                    categ._eai_rt_require(accounts, ['input', 'claim'])
                    is_claim, account = line._eai_rt_refund_target(accounts, strict=True)
                    vals['eai_rt_is_claim'] = is_claim
                    vals['eai_rt_role'] = 'claim' if is_claim and accounts['claim_is_separate'] else 'input'
                    if is_claim:
                        categ._eai_rt_require(accounts, ['price_diff'])
                else:
                    categ._eai_rt_require(accounts, ['input'])
                    account = accounts['input']
                    vals['eai_rt_role'] = 'input'
                account = self.fiscal_position_id.map_account(account)
                if line.account_id != account:
                    vals['account_id'] = account.id
            elif self.is_sale_document(include_receipts=True):
                categ._eai_rt_require(accounts, ['output', 'expense'])
                sale_orders = line.sale_line_ids.order_id
                vals['eai_rt_origin_ref'] = ', '.join(sale_orders.mapped('name')) or self.name
                vals['eai_rt_warehouse_id'] = sale_orders[:1].warehouse_id.id
            if vals:
                line.write(vals)

    # ------------------------------------------------------------------
    # COGS / HPP (sisi penjualan) dan penutupan klaim (sisi pembelian)
    # ------------------------------------------------------------------
    def _stock_account_prepare_realtime_out_lines_vals(self):
        """HPP invoice final: sisi kredit memakai Stock Output (bukan Stock Account) untuk
        kategori bertanda. Nilainya tetap dihitung standar Odoo 19 dari nilai DO."""
        vals_list = super()._stock_account_prepare_realtime_out_lines_vals()
        for vals in vals_list:
            if not vals.get('cogs_origin_id'):
                continue
            origin = self.env['account.move.line'].browse(vals['cogs_origin_id'])
            if not origin._eai_rt_enabled():
                continue
            move = origin.move_id
            std_accounts = origin.product_id.product_tmpl_id.get_product_accounts(fiscal_pos=move.fiscal_position_id)
            vals['eai_rt_origin_ref'] = origin.eai_rt_origin_ref
            vals['eai_rt_warehouse_id'] = origin.eai_rt_warehouse_id.id
            if std_accounts['stock_valuation'] and vals['account_id'] == std_accounts['stock_valuation'].id:
                output = move.fiscal_position_id.map_account(origin._eai_rt_accounts()['output'])
                vals['account_id'] = output.id
                vals['eai_rt_role'] = 'output'
        return vals_list

    def _eai_rt_claim_difference_lines_vals(self):
        """Credit note ANTAM menutup klaim pada nilai klaim, bukan nilai credit note.

        Klaim dicatat saat retur (qty x harga bill asal). Bila credit note bernilai lain,
        selisihnya dipindahkan dari Piutang Klaim ke akun selisih harga retur, sehingga
        saldo klaim per PO line kembali nol. Baris dibuat sebagai baris 'cogs' supaya
        ikut terhapus bila credit note dikembalikan ke draft. Baris 'cogs' Odoo 19 selalu
        dalam mata uang perusahaan, jadi amount_currency = balance (juga untuk credit note
        valuta asing; selisih kurs terhadap klaim ikut masuk ke akun selisih harga retur).
        """
        self.ensure_one()
        vals_list = []
        for line in self.invoice_line_ids.filtered('eai_rt_is_claim'):
            pol = line.purchase_line_id
            returns = pol.move_ids.filtered(
                lambda m: m.state == 'done' and m.is_out and m.location_dest_id.usage == 'supplier' and m.eai_rt_claim_value)
            returned_qty = sum(returns.mapped(lambda m: m._get_valued_qty()))
            if not returned_qty:
                continue
            claim_unit = sum(returns.mapped('eai_rt_claim_value')) / returned_qty
            expected = self.company_currency_id.round(claim_unit * line._eai_rt_qty_product_uom())
            diff = self.company_currency_id.round(expected - abs(line.balance))
            if self.company_currency_id.is_zero(diff):
                continue
            accounts = line._eai_rt_accounts()
            common = {
                'name': self.env._("Selisih klaim retur: %(name)s", name=(line.name or '')[:64]),
                'move_id': self.id,
                'partner_id': self.commercial_partner_id.id,
                'product_id': line.product_id.id,
                'product_uom_id': line.product_uom_id.id,
                # Selisih nilai saja, tanpa qty (qty klaim sudah ditutup oleh baris credit note).
                'quantity': 0.0,
                'display_type': 'cogs',
                'tax_ids': [],
                'cogs_origin_id': line.id,
                'analytic_distribution': line.analytic_distribution,
                'eai_rt_origin_ref': line.eai_rt_origin_ref,
                'eai_rt_warehouse_id': line.eai_rt_warehouse_id.id,
            }
            vals_list.append({
                **common, 'account_id': line.account_id.id,
                'balance': -diff, 'amount_currency': -diff,
                'eai_rt_role': 'claim' if accounts['claim_is_separate'] else 'input',
            })
            vals_list.append({
                **common, 'account_id': self.fiscal_position_id.map_account(accounts['price_diff']).id,
                'balance': diff, 'amount_currency': diff, 'eai_rt_role': 'other',
            })
        return vals_list
