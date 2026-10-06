from collections import defaultdict

from odoo import api, fields, models
from odoo.tools import frozendict

class ProductTemplate(models.Model):
    _inherit = 'product.template'
    property_trade_receivable_account_id = fields.Many2one('account.account', string='Customer Receivable Account', company_dependent=True, check_company=True, domain="[('account_type', '=', 'asset_receivable')]")
    property_trade_payable_account_id = fields.Many2one('account.account', string='Vendor Payable Account', company_dependent=True, check_company=True, domain="[('account_type', '=', 'liability_payable')]")

class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    @api.depends('date_maturity', 'account_id')
    def _compute_term_key(self):
        super()._compute_term_key()
        for line in self:
            if line.display_type == 'payment_term' and line.account_id:
                line.term_key = frozendict({'move_id': line.move_id.id, 'date_maturity': fields.Date.to_date(line.date_maturity), 'discount_date': line.discount_date, 'account_id': line.account_id.id})

    def _get_installments_data(self, *args, **kwargs):
        installments = super()._get_installments_data(*args, **kwargs)
        # Odoo numbers each payment-term line as its own installment. Lines split
        # only to use different AR/AP accounts must stay together when due together.
        by_due_date = defaultdict(list)
        for item in installments:
            line = item.get('line')
            if line and line.display_type == 'payment_term' and not item.get('reconciled') and item.get('type') != 'early_payment_discount':
                by_due_date[item.get('date_maturity')].append(item)
        for same_date in by_due_date.values():
            if len(same_date) < 2:
                continue
            modes = {item.get('type') for item in same_date}
            if 'before_date' in modes:
                for item in same_date:
                    if item.get('type') not in ('overdue', 'early_payment_discount'):
                        item['type'] = 'before_date'
            elif 'overdue' in modes:
                for item in same_date:
                    if item.get('type') not in ('early_payment_discount',):
                        item['type'] = 'overdue'
            elif 'next' in modes:
                next_item = next(item for item in same_date if item.get('type') == 'next')
                for item in same_date:
                    if item is not next_item:
                        # _get_total_amounts_to_pay adds overdue items to the same
                        # default payment amount while retaining each AML for matching.
                        item['type'] = 'overdue'
        return installments

class AccountMove(models.Model):
    _inherit = 'account.move'
    @api.depends('invoice_payment_term_id', 'invoice_date', 'currency_id', 'amount_total_in_currency_signed', 'invoice_date_due', 'invoice_line_ids.price_total', 'invoice_line_ids.product_id.property_trade_receivable_account_id', 'invoice_line_ids.product_id.property_trade_payable_account_id', 'fiscal_position_id', 'partner_id')
    def _compute_needed_terms(self):
        super()._compute_needed_terms()
        for move in self.filtered(lambda m: m.is_invoice(include_receipts=True) and m.invoice_line_ids and m.needed_terms):
            weights = {}
            for line in move.invoice_line_ids:
                if move.is_sale_document(include_receipts=True):
                    account = line.product_id.property_trade_receivable_account_id or move.partner_id.property_account_receivable_id
                else:
                    account = line.product_id.property_trade_payable_account_id or move.partner_id.property_account_payable_id
                if move.fiscal_position_id and account:
                    account = move.fiscal_position_id.map_account(account)
                if account:
                    weights[account.id] = weights.get(account.id, 0.0) + abs(line.price_total)
            if not weights or not sum(weights.values()):
                continue
            total_weight = sum(weights.values())
            split = {}
            for key, values in move.needed_terms.items():
                key = dict(key)
                left = {name: values.get(name, 0.0) for name in ('balance', 'amount_currency', 'discount_balance', 'discount_amount_currency')}
                ids = list(weights)
                for idx, account_id in enumerate(ids):
                    ratio = weights[account_id] / total_weight
                    vals = dict(values)
                    for name, remainder in tuple(left.items()):
                        amount = remainder if idx == len(ids) - 1 else values.get(name, 0.0) * ratio
                        vals[name] = amount
                        left[name] -= amount
                    split[frozendict({**key, 'account_id': account_id})] = vals
            move.needed_terms = split
