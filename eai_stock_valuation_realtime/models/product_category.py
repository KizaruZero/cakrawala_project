from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError

ACCOUNT_DOMAIN = [
    ('account_type', 'not in', ('asset_receivable', 'liability_payable', 'asset_cash', 'liability_credit_card', 'off_balance')),
]


class ProductCategory(models.Model):
    _inherit = 'product.category'

    eai_rt_enabled = fields.Boolean(
        string='Real-time Valuation',
        help="When enabled, every stock move of products in this category is posted immediately "
             "through the interim Stock Input / Stock Output accounts. "
             "Categories without this option keep the standard Odoo behaviour.",
        tracking=True,
    )
    eai_rt_stock_input_account_id = fields.Many2one(
        'account.account', string='Stock Input Account', company_dependent=True,
        ondelete='restrict', check_company=True, domain=ACCOUNT_DOMAIN,
        help="Interim receipt account (e.g. Goods in Transit). "
             "Debited by the vendor bill, credited when goods are received.")
    eai_rt_stock_output_account_id = fields.Many2one(
        'account.account', string='Stock Output Account', company_dependent=True,
        ondelete='restrict', check_company=True, domain=ACCOUNT_DOMAIN,
        help="Interim delivery account (e.g. Goods Delivered Not Invoiced). "
             "Debited by the delivery, credited by the final customer invoice (COGS).")
    eai_rt_price_diff_account_id = fields.Many2one(
        'account.account', string='Return Price Difference Account', company_dependent=True,
        ondelete='restrict', check_company=True, domain=ACCOUNT_DOMAIN,
        help="Difference between average cost and bill price on purchase returns, and between "
             "the vendor credit note and the claim value. Empty = company default.")
    eai_rt_claim_account_id = fields.Many2one(
        'account.account', string='Return Claim Account', company_dependent=True,
        ondelete='restrict', check_company=True, domain=ACCOUNT_DOMAIN,
        help="Holds the value of goods returned to the vendor until the credit note is received. "
             "Empty = company default; if both are empty, Stock Input is used.")
    eai_rt_inventory_diff_account_id = fields.Many2one(
        'account.account', string='Inventory Adjustment Account', company_dependent=True,
        ondelete='restrict', check_company=True, domain=ACCOUNT_DOMAIN,
        help="Counterpart of inventory adjustments (stock count). Empty = company default.")
    eai_rt_scrap_account_id = fields.Many2one(
        'account.account', string='Scrap Account', company_dependent=True,
        ondelete='restrict', check_company=True, domain=ACCOUNT_DOMAIN,
        help="Counterpart of scrapped goods. Empty = company default, then the Inventory Adjustment Account.")

    # ------------------------------------------------------------------
    # Konsistensi konfigurasi
    # ------------------------------------------------------------------
    @api.constrains('eai_rt_enabled')
    def _check_eai_rt_enabled(self):
        self._eai_rt_check_config()

    @api.model_create_multi
    def create(self, vals_list):
        categs = super().create(vals_list)
        categs.filtered('eai_rt_enabled')._eai_rt_init_existing_moves()
        return categs

    def write(self, vals):
        newly_enabled = self.filtered(lambda c: not c.eai_rt_enabled) if vals.get('eai_rt_enabled') else self.browse()
        res = super().write(vals)
        if self.filtered('eai_rt_enabled') and {
            'eai_rt_enabled', 'property_valuation', 'property_cost_method',
        } & set(vals):
            self._eai_rt_check_config()
        newly_enabled._eai_rt_init_existing_moves()
        return res

    def _eai_rt_init_existing_moves(self):
        """Saat flag diaktifkan pada kategori yang sudah punya transaksi, nilai move lama
        dianggap sudah tercermin di GL (lewat mekanisme standar). Hanya perubahan nilai
        setelah titik ini yang dijurnal, supaya tidak ada jurnal ganda."""
        if not self:
            return
        products = self.env['product.product'].with_context(active_test=False).search([('categ_id', 'in', self.ids)])
        self.env['stock.move']._eai_rt_mark_as_posted(products)

    def _eai_rt_check_config(self):
        for categ in self.filtered('eai_rt_enabled'):
            if categ.property_valuation != 'real_time':
                raise ValidationError(self.env._(
                    "Kategori '%(categ)s': valuasi real-time hanya boleh dipakai "
                    "bila Inventory Valuation = Perpetual (at invoicing).", categ=categ.display_name))
            if categ.property_cost_method != 'average':
                raise ValidationError(self.env._(
                    "Kategori '%(categ)s': valuasi real-time hanya mendukung "
                    "Costing Method = Average Cost (AVCO).", categ=categ.display_name))

    def _eai_rt_get_accounts(self, company=None):
        """Akun yang dipakai mesin valuasi real-time untuk kategori ini.

        Field yang kosong di kategori diambil dari setting company (klaim, selisih, rusak).
        Tidak memvalidasi kelengkapan; lihat `_eai_rt_require`.
        """
        self.ensure_one()
        company = company or self.env.company
        categ = self.with_company(company)
        stock = categ.property_stock_valuation_account_id or company.account_stock_valuation_id
        input_acc = categ.eai_rt_stock_input_account_id
        claim = categ.eai_rt_claim_account_id or company.eai_rt_claim_account_id
        inventory_diff = categ.eai_rt_inventory_diff_account_id or company.eai_rt_inventory_diff_account_id
        return {
            'stock': stock,
            'input': input_acc,
            'output': categ.eai_rt_stock_output_account_id,
            'expense': categ.property_account_expense_categ_id or company.expense_account_id,
            'price_diff': categ.eai_rt_price_diff_account_id or company.eai_rt_price_diff_account_id,
            # Tanpa akun klaim: perilaku v17 murni, klaim ditampung di Stock Input.
            'claim': claim or input_acc,
            'claim_is_separate': bool(claim) and claim != input_acc,
            'inventory_diff': inventory_diff,
            'scrap': categ.eai_rt_scrap_account_id or company.eai_rt_scrap_account_id or inventory_diff,
            'journal': categ.property_stock_journal or company.account_stock_journal_id,
        }

    def _eai_rt_require(self, accounts, keys):
        """Raise pesan yang jelas bila akun yang dibutuhkan belum diisi."""
        self.ensure_one()
        labels = {
            'stock': self.env._('Stock Account'),
            'input': self.env._('Stock Input Account'),
            'output': self.env._('Stock Output Account'),
            'expense': self.env._('Expense Account'),
            'price_diff': self.env._('Return Price Difference Account'),
            'claim': self.env._('Return Claim Account / Stock Input Account'),
            'inventory_diff': self.env._('Inventory Adjustment Account'),
            'scrap': self.env._('Scrap Account / Inventory Adjustment Account'),
            'journal': self.env._('Stock Journal (Inventory Valuation)'),
        }
        missing = [labels[k] for k in keys if not accounts.get(k)]
        if missing:
            raise UserError(self.env._(
                "Konfigurasi valuasi real-time belum lengkap untuk kategori '%(categ)s'. "
                "Lengkapi: %(missing)s.", categ=self.display_name, missing=', '.join(missing)))
