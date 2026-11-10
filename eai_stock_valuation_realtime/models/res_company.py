from collections import defaultdict

from odoo import fields, models
from odoo.fields import Domain

from .product_category import ACCOUNT_DOMAIN


class ResCompany(models.Model):
    _inherit = 'res.company'

    eai_rt_claim_account_id = fields.Many2one(
        'account.account', string='Default Return Claim Account',
        check_company=True, domain=ACCOUNT_DOMAIN,
        help="Used by real-time valuation categories that do not set their own account.")
    eai_rt_price_diff_account_id = fields.Many2one(
        'account.account', string='Default Return Price Difference Account',
        check_company=True, domain=ACCOUNT_DOMAIN)
    eai_rt_inventory_diff_account_id = fields.Many2one(
        'account.account', string='Default Inventory Adjustment Account',
        check_company=True, domain=ACCOUNT_DOMAIN)
    eai_rt_scrap_account_id = fields.Many2one(
        'account.account', string='Default Scrap Account',
        check_company=True, domain=ACCOUNT_DOMAIN)
    eai_rt_auto_post = fields.Boolean(
        string='Auto-post Real-time Valuation Entries', default=True,
        help="When unchecked, entries from stock moves are created as Draft for Finance review.")

    # ------------------------------------------------------------------
    # Pengecualian dari Stock Closing
    # ------------------------------------------------------------------
    def _eai_rt_flagged_products(self):
        self.ensure_one()
        return self.env['product.product'].sudo().with_company(self).with_context(active_test=False).search([
            ('categ_id.eai_rt_enabled', '=', True),
        ])

    def action_close_stock_valuation(self, at_date=None, auto_post=False):
        # Kategori bertanda sudah dijurnal per stock move: keluarkan dari Stock Closing
        # (Stock Variation global dan variasi periode) agar tidak dikoreksi dua kali.
        return super(ResCompany, self.with_context(eai_rt_exclude_flagged=True)).action_close_stock_valuation(
            at_date=at_date, auto_post=auto_post)

    def _action_close_stock_valuation(self, at_date=None):
        return super(ResCompany, self.with_context(eai_rt_exclude_flagged=True))._action_close_stock_valuation(at_date=at_date)

    def _get_accounts_by_product(self, products=None):
        accounts_by_product = super()._get_accounts_by_product(products=products)
        if self.env.context.get('eai_rt_exclude_flagged'):
            accounts_by_product = {
                product: accounts for product, accounts in accounts_by_product.items()
                if not product.categ_id.eai_rt_enabled
            }
        return accounts_by_product

    def stock_accounting_value(self, accounts_by_product=None, at_date=None):
        if not self.env.context.get('eai_rt_exclude_flagged'):
            return super().stock_accounting_value(accounts_by_product=accounts_by_product, at_date=at_date)
        # Salinan logika standar + pengecualian baris jurnal milik produk bertanda.
        self.ensure_one()
        if not accounts_by_product:
            accounts_by_product = self._get_accounts_by_product()
        stock_valuation_accounts_ids = {
            accounts['valuation'].id for accounts in accounts_by_product.values() if accounts['valuation']
        }
        flagged = self._eai_rt_flagged_products()
        domain = Domain([
            ('account_id', 'in', list(stock_valuation_accounts_ids)),
            ('company_id', '=', self.id),
            ('parent_state', '=', 'posted'),
        ])
        if flagged:
            domain &= Domain(['|', ('product_id', '=', False), ('product_id', 'not in', flagged.ids)])
        if at_date:
            domain &= Domain([('date', '<=', at_date)])
        account_data = defaultdict(float)
        for account, balance in self.env['account.move.line']._read_group(domain, ['account_id'], ['balance:sum']):
            account_data[account] += balance
        return account_data
