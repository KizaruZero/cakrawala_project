# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class LeasingVoucherPayWizard(models.TransientModel):
    _name = 'leasing.voucher.pay.wizard'
    _description = 'Leasing Voucher Pay Installments Wizard'

    voucher_id = fields.Many2one('leasing.payment.voucher', required=True, readonly=True)
    journal_id = fields.Many2one(
        'account.journal',
        string='Outgoing Bank Journal',
        required=True,
        domain="[('type', 'in', ('bank', 'cash'))]"
    )
    payment_date = fields.Date(
        string='Payment Date',
        required=True,
        default=fields.Date.context_today
    )

    def action_confirm_payment(self):
        self.ensure_one()
        voucher = self.voucher_id
        if voucher.state != 'approved':
            raise UserError(_("Hanya voucher dengan status Approved yang dapat dibayar."))
        if voucher.settlement_state == 'paid':
            raise UserError(_("Voucher ini sudah lunas/terbayar."))

        default_account = self.journal_id.default_account_id
        if not default_account:
            raise UserError(_("Jurnal Bank/Kas yang dipilih tidak memiliki Default Account."))

        voucher_lines = voucher.line_ids
        if not voucher_lines:
            raise UserError(_("Tidak ada baris angsuran leasing dalam voucher ini."))

        # Validate accounts on each loan
        for vline in voucher_lines:
            loan = vline.loan_id
            if not loan.long_term_account_id:
                raise UserError(_(
                    "Missing 'Hutang Pokok' account on the loan for installment %s (Leasing: %s)",
                    vline.installment_number, loan.agreement_no or loan.name
                ))
            if not loan.accrued_interest_account_id:
                raise UserError(_(
                    "Missing 'Hutang Bunga Sementara' account on the loan for installment %s (Leasing: %s)",
                    vline.installment_number, loan.agreement_no or loan.name
                ))

        created_moves = self.env['account.move']
        loans = voucher_lines.mapped('loan_id')

        for loan in loans:
            loan_vlines = voucher_lines.filtered(lambda l: l.loan_id == loan)
            move_lines = []
            total_payment = 0.0

            analytic_dist = {str(loan.analytic_account_id.id): 100} if loan.analytic_account_id else False

            for vline in loan_vlines:
                # Principal Debit Line
                if vline.principal > 0:
                    move_lines.append((0, 0, {
                        'name': f"Angsuran ke-{vline.installment_number} - Principal",
                        'account_id': loan.long_term_account_id.id,
                        'debit': vline.principal,
                        'credit': 0.0,
                        'partner_id': loan.vendor_id.id if loan.vendor_id else False,
                        'analytic_distribution': analytic_dist,
                    }))
                    total_payment += vline.principal

                # Interest Debit Line
                if vline.interest > 0:
                    move_lines.append((0, 0, {
                        'name': f"Angsuran ke-{vline.installment_number} - Interest",
                        'account_id': loan.accrued_interest_account_id.id,
                        'debit': vline.interest,
                        'credit': 0.0,
                        'partner_id': loan.vendor_id.id if loan.vendor_id else False,
                        'analytic_distribution': analytic_dist,
                    }))
                    total_payment += vline.interest

            if total_payment <= 0:
                continue

            # Bank Credit Line for this Loan
            move_lines.append((0, 0, {
                'name': f"[{voucher.name}] Pembayaran Angsuran Leasing - {loan.agreement_no or loan.name}",
                'account_id': default_account.id,
                'debit': 0.0,
                'credit': total_payment,
                'partner_id': loan.vendor_id.id if loan.vendor_id else False,
                'analytic_distribution': analytic_dist,
            }))

            move_vals = {
                'move_type': 'entry',
                'journal_id': self.journal_id.id,
                'date': self.payment_date,
                'ref': f"[{voucher.name}] Leasing Payment {loan.agreement_no or loan.name}",
                'partner_id': loan.vendor_id.id if loan.vendor_id else False,
                'line_ids': move_lines,
            }

            move = self.env['account.move'].create(move_vals)
            move.action_post()
            created_moves |= move

            # Link move to loan lines and voucher lines
            for vline in loan_vlines:
                vline.payment_move_id = move.id
                if vline.loan_line_id:
                    vline.loan_line_id.write({
                        'vendor_bill_id': move.id,
                        'payment_date': self.payment_date,
                    })

        # Update voucher state
        voucher.write({
            'state': 'paid',
            'settlement_state': 'paid',
        })

        moves_links = ", ".join([m._get_html_link() for m in created_moves])
        voucher._log('paid', _('Pembayaran angsuran berhasil dilakukan. Journal Entries: %s') % moves_links)

        return {'type': 'ir.actions.act_window_close'}
