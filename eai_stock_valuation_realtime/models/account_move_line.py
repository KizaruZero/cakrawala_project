from odoo import fields, models
from odoo.exceptions import UserError


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    eai_rt_role = fields.Selection([
        ('stock', 'Persediaan'),
        ('input', 'Stock Input (dalam perjalanan)'),
        ('output', 'Stock Output (terkirim belum ditagih)'),
        ('claim', 'Piutang Klaim Retur'),
        ('other', 'Lainnya'),
    ], string='Peran Valuasi RT', copy=False, readonly=True, index='btree_not_null')
    eai_rt_origin_ref = fields.Char('Dokumen Asal (RT)', copy=False, readonly=True, index='btree_not_null')
    eai_rt_warehouse_id = fields.Many2one('stock.warehouse', 'Gudang/Butik (RT)', copy=False, readonly=True)
    eai_rt_is_claim = fields.Boolean(
        'Menutup Klaim Retur', copy=False, readonly=True,
        help="Baris credit note vendor yang menutup Piutang Klaim Retur (qty yang sudah diretur).")

    # ------------------------------------------------------------------
    def _eai_rt_enabled(self):
        self.ensure_one()
        product = self.product_id.with_company(self.company_id)
        return bool(product and product.is_storable and product.categ_id.eai_rt_enabled
                    and product.valuation == 'real_time')

    def _eai_rt_accounts(self):
        self.ensure_one()
        return self.product_id.categ_id._eai_rt_get_accounts(self.company_id)

    def _eai_rt_qty_product_uom(self):
        self.ensure_one()
        return self.product_uom_id._compute_quantity(self.quantity, self.product_id.uom_id)

    def _eai_rt_returned_pending_qty(self):
        """Qty yang sudah diretur ke vendor pada PO line ini tetapi belum ditutup credit note."""
        self.ensure_one()
        pol = self.purchase_line_id
        if not pol:
            return 0.0
        returned = sum(
            m._get_valued_qty() for m in pol.move_ids
            if m.state == 'done' and m.is_out and m.location_dest_id.usage == 'supplier'
        )
        # Qty yang sudah menutup klaim: credit note lain yang sudah diposting, ditambah baris lain
        # pada credit note yang sama (yang sedang diposting) untuk PO line ini.
        closed = sum(
            l._eai_rt_qty_product_uom() for l in pol.invoice_lines
            if l != self and l.eai_rt_is_claim and l.move_type == 'in_refund'
            and (l.parent_state == 'posted' or l.move_id == self.move_id)
        )
        return returned - closed

    def _eai_rt_refund_target(self, accounts, strict=False):
        """(is_claim, akun) untuk baris credit note vendor kategori bertanda."""
        self.ensure_one()
        uom = self.product_id.uom_id
        pending = self._eai_rt_returned_pending_qty()
        if uom.compare(pending, 0) <= 0:
            return False, accounts['input']
        qty = self._eai_rt_qty_product_uom()
        if strict and uom.compare(qty, pending) > 0:
            raise UserError(self.env._(
                "Credit note %(move)s, produk %(product)s: qty %(qty)s melebihi qty retur yang belum "
                "di-credit-note (%(pending)s). Pisahkan baris menjadi qty retur (menutup klaim) dan qty "
                "yang belum pernah diterima.",
                move=self.move_id.display_name, product=self.product_id.display_name,
                qty=qty, pending=pending))
        return True, accounts['claim']

    # ------------------------------------------------------------------
    # Akun baris bill / credit note vendor
    # ------------------------------------------------------------------
    def _compute_account_id(self):
        super()._compute_account_id()
        for line in self:
            if line.display_type != 'product' or not line.product_id:
                continue
            move = line.move_id
            if not move.is_purchase_document(include_receipts=True):
                continue
            if not line._eai_rt_enabled() or not line._eligible_for_stock_account():
                continue
            accounts = line._eai_rt_accounts()
            if move.move_type == 'in_refund':
                account = line._eai_rt_refund_target(accounts)[1]
            else:
                account = accounts['input']
            if account:
                line.account_id = move.fiscal_position_id.map_account(account)
