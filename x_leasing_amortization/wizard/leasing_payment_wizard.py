from odoo import models, fields, api, _
from odoo.exceptions import UserError

class LeasingPaymentWizardLine(models.TransientModel):
    _name = 'leasing.payment.wizard.line'
    _description = 'Leasing Payment Wizard Line'

    wizard_id = fields.Many2one('leasing.payment.wizard')
    is_selected = fields.Boolean(string="Pilih", default=False)
    loan_line_id = fields.Many2one('account.loan.line', required=True)
    
    # Related fields for display
    installment_number = fields.Integer(related='loan_line_id.installment_number', string="No.")
    date = fields.Date(related='loan_line_id.date', string="Date")
    principal = fields.Monetary(related='loan_line_id.principal', string="Principals")
    interest = fields.Monetary(related='loan_line_id.interest', string="Interests")
    payment = fields.Monetary(related='loan_line_id.payment', string="Payments")
    currency_id = fields.Many2one(related='loan_line_id.currency_id')

class LeasingPaymentWizard(models.TransientModel):
    _name = 'leasing.payment.wizard'
    _description = 'Leasing Payment Wizard'

    loan_id = fields.Many2one('account.loan', string='Loan')
    journal_id = fields.Many2one(
        'account.journal', 
        string='Outgoing Bank Journal', 
        required=True,
        domain="[('type', 'in', ('bank', 'cash'))]"
    )
    payment_date = fields.Date(string='Payment Date', required=True, default=fields.Date.context_today)
    line_ids = fields.One2many(
        'leasing.payment.wizard.line',
        'wizard_id',
        string='Installments'
    )

    def action_confirm_payment(self):
        self.ensure_one()
        selected_lines = self.line_ids.filtered('is_selected').mapped('loan_line_id')
        
        if not selected_lines:
            raise UserError(_("Silakan centang minimal satu angsuran untuk dibayar!"))

        # Validate that all lines have the required accounts set on their loan
        for line in selected_lines:
            if not line.loan_id.long_term_account_id:
                raise UserError(_("Missing 'Hutang Pokok' account on the loan for installment %s", line.installment_number))
            if not line.loan_id.accrued_interest_account_id:
                raise UserError(_("Missing 'Hutang Bunga Sementara' account on the loan for installment %s", line.installment_number))

        move_lines = []
        total_payment = 0.0

        for line in selected_lines:
            loan = line.loan_id
            
            # Principal Debit Line
            if line.principal > 0:
                move_lines.append((0, 0, {
                    'name': f"Angsuran ke-{line.installment_number} - Principal",
                    'account_id': loan.long_term_account_id.id,
                    'debit': line.principal,
                    'credit': 0.0,
                    'partner_id': loan.vendor_id.id if loan.vendor_id else False,
                }))
                total_payment += line.principal
            
            # Interest Debit Line
            if line.interest > 0:
                move_lines.append((0, 0, {
                    'name': f"Angsuran ke-{line.installment_number} - Interest",
                    'account_id': loan.accrued_interest_account_id.id,
                    'debit': line.interest,
                    'credit': 0.0,
                    'partner_id': loan.vendor_id.id if loan.vendor_id else False,
                }))
                total_payment += line.interest

        if total_payment <= 0:
            raise UserError(_("Total payment amount must be greater than zero."))

        # Bank Credit Line
        default_account = self.journal_id.default_account_id
        if not default_account:
            raise UserError(_("The selected Bank Journal does not have a default account."))

        move_lines.append((0, 0, {
            'name': _("Pembayaran Angsuran Leasing"),
            'account_id': default_account.id,
            'debit': 0.0,
            'credit': total_payment,
        }))

        # Create Journal Entry
        move_vals = {
            'move_type': 'entry',
            'journal_id': self.journal_id.id,
            'date': self.payment_date,
            'ref': _("Leasing Payment"),
            'line_ids': move_lines,
        }
        
        move = self.env['account.move'].create(move_vals)
        move.action_post()

        # Link move to loan lines
        for line in selected_lines:
            line.vendor_bill_id = move.id
            line.payment_date = self.payment_date

        return {'type': 'ir.actions.act_window_close'}
