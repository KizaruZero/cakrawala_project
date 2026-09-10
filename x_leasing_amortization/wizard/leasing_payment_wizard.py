from odoo import models, fields, api, _
from odoo.exceptions import UserError

class LeasingPaymentWizard(models.TransientModel):
    _name = 'leasing.payment.wizard'
    _description = 'Leasing Payment Wizard'
    journal_id = fields.Many2one(
        'account.journal', 
        string='Outgoing Bank Journal', 
        required=True,
        domain="[('type', 'in', ('bank', 'cash'))]"
    )
    payment_date = fields.Date(string='Payment Date', required=True, default=fields.Date.context_today)
    def action_confirm_payment(self):
        self.ensure_one()
        active_ids = self.env.context.get('active_ids', [])
        if not active_ids:
            raise UserError(_("Silakan centang minimal satu angsuran untuk dibayar!"))

        selected_lines = self.env['account.loan.line'].browse(active_ids)
        
        # Check if any line is already paid
        already_paid = selected_lines.filtered(lambda l: l.vendor_bill_id)
        if already_paid:
            paid_info = ", ".join([f"Angsuran ke-{l.installment_number} (Leasing: {l.loan_id.agreement_no})" for l in already_paid])
            raise UserError(_("Beberapa angsuran yang Anda pilih sudah terbayar (memiliki Jurnal):\n%s", paid_info))

        # Validate accounts
        for line in selected_lines:
            if not line.loan_id.long_term_account_id:
                raise UserError(_("Missing 'Hutang Pokok' account on the loan for installment %s (Leasing: %s)", line.installment_number, line.loan_id.agreement_no))
            if not line.loan_id.accrued_interest_account_id:
                raise UserError(_("Missing 'Hutang Bunga Sementara' account on the loan for installment %s (Leasing: %s)", line.installment_number, line.loan_id.agreement_no))

        # Group lines by loan_id (Option A)
        loans = selected_lines.mapped('loan_id')
        
        default_account = self.journal_id.default_account_id
        if not default_account:
            raise UserError(_("The selected Bank Journal does not have a default account."))

        for loan in loans:
            loan_lines = selected_lines.filtered(lambda l: l.loan_id == loan)
            move_lines = []
            total_payment = 0.0
            
            for line in loan_lines:
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
                continue

            # Bank Credit Line for this Loan
            move_lines.append((0, 0, {
                'name': f"Pembayaran Angsuran Leasing - {loan.agreement_no}",
                'account_id': default_account.id,
                'debit': 0.0,
                'credit': total_payment,
                'partner_id': loan.vendor_id.id if loan.vendor_id else False,
            }))

            # Create Journal Entry
            move_vals = {
                'move_type': 'entry',
                'journal_id': self.journal_id.id,
                'date': self.payment_date,
                'ref': f"Leasing Payment {loan.agreement_no}",
                'partner_id': loan.vendor_id.id if loan.vendor_id else False,
                'line_ids': move_lines,
            }
            
            move = self.env['account.move'].create(move_vals)
            move.action_post()

            # Link move to loan lines
            for line in loan_lines:
                line.vendor_bill_id = move.id
                line.payment_date = self.payment_date

        return {'type': 'ir.actions.act_window_close'}
