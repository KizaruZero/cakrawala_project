from odoo import models, fields, api

class AccountPayment(models.Model):
    _inherit = 'account.payment'

    asset_id = fields.Many2one('account.asset', string="Asset Link")

    def write(self, vals):
        res = super(AccountPayment, self).write(vals)
        for payment in self:
            if payment.asset_id:
                # Find draft invoices linked to this asset
                draft_invoices = self.env['account.move'].search([
                    ('asset_id', '=', payment.asset_id.id),
                    ('move_type', '=', 'out_invoice'),
                    ('state', '=', 'draft')
                ])
                if draft_invoices:
                    inv_vals = {}
                    if 'partner_id' in vals or payment.partner_id:
                        inv_vals['partner_id'] = payment.partner_id.id
                    if inv_vals:
                        draft_invoices.write(inv_vals)
                    
                    if 'amount' in vals or payment.amount:
                        for inv in draft_invoices:
                            for line in inv.invoice_line_ids:
                                line.write({'price_unit': payment.amount})
                    
                    if vals.get('state') in ('in_process', 'posted'):
                        for inv in draft_invoices:
                            try:
                                inv.action_post()
                            except Exception as e:
                                pass
        return res
