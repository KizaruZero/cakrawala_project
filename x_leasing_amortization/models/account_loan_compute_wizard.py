from odoo import models, fields, _, api
from odoo.tools.misc import format_date

class AccountLoanComputeWizard(models.TransientModel):
    _inherit = 'account.loan.compute.wizard'
    _description = 'Preview of Amortization Table'

    @api.depends('loan_amount','interest_rate','loan_term','start_date',
                 'first_payment_date','payment_end_of_month','compounding_method')
    def _compute_preview(self):
        for wizard in self:
            if wizard.loan_amount and wizard.loan_term and wizard.start_date:
                schedule = wizard._get_loan_payment_schedule()
                if not schedule:
                    wizard.preview = ''
                    continue
                fmt = wizard.currency_id.format
                interest_list = [float(p.interest_amount) for p in schedule]
                saldo_bunga = []
                total_remaining = sum(interest_list)
                for interest in interest_list:
                    total_remaining -= interest
                    saldo_bunga.append(max(total_remaining,0))
                header = (
                    f"{'Angs. ke': <10} "
                    f"{'Tanggal': <12} "
                    f"{'Pokok': >15} "
                    f"{'Bunga': >15} "
                    f"{'Total': >15} "
                    f"{'Saldo Pokok': >15} "
                    f"{'Saldo Bunga': >15}\n"
                )
                def row(num, payment, s_bunga):
                    return(
                        f"{num: <10} "
                        f"{format_date(self.env, payment.date): <12} "
                        f"{fmt(float(payment.principal_amount)):>15} "
                        f"{fmt(float(payment.interest_amount)):>15} "
                        f"{fmt(float(payment.payment_amount)):>15} "
                        f"{fmt(float(payment.loan_balance_amount)):>15} "
                        f"{fmt(float(s_bunga)):>15}\n"
                    )
                preview = header
                for i, payment in enumerate(schedule[:5]):
                    preview += row(i+1, payment, saldo_bunga[i])
                if len(schedule) > 10:
                    preview += f"{'...': <10} {'...': <12} {'...': >15} {'...': >15} {'...': >15} {'...': >15} {'...': >15}\n"
                for i, payment in enumerate(schedule[-5:]):
                    idx = len(schedule)-5+i
                    preview += row(idx+1, payment, saldo_bunga[idx])
                wizard.preview = preview
            else:
                wizard.preview = ''