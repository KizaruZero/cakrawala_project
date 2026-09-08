from odoo import models, fields, _, api
from odoo.tools.misc import format_date
from dateutil.relativedelta import relativedelta

class AccountLoanComputeWizard(models.TransientModel):
    _inherit = 'account.loan.compute.wizard'
    _description = 'Preview of Amortization Table'

    compute_method = fields.Selection(
        selection=[
            ('effective', 'Bunga Efektif'),
            ('flat', 'Bunga Flat'),
        ],
        string='Compute Method',
        default='effective',
    )

    @api.model
    def default_get(self, fields_list):
        res = super(AccountLoanComputeWizard, self).default_get(fields_list)
        active_id = self.env.context.get('active_id') or self.env.context.get('default_loan_id')
        active_model = self.env.context.get('active_model')
        if active_id and (not active_model or active_model == 'account.loan'):
            loan = self.env['account.loan'].browse(active_id)
            if loan.exists():
                if hasattr(loan, 'total_hutang') and loan.total_hutang:
                    res['loan_amount'] = loan.total_hutang
                rate = loan.interest_rate_annual if (hasattr(loan, 'interest_rate_annual') and loan.interest_rate_annual) else 0.0
                if 0 < rate <= 100:
                    res['interest_rate'] = rate
                else:
                    res['interest_rate'] = 1.0
                if hasattr(loan, 'start_date_leasing') and loan.start_date_leasing:
                    res['start_date'] = loan.start_date_leasing
                if hasattr(loan, 'duration') and loan.duration:
                    res['loan_term'] = int(round(loan.duration / 12.0))
                if hasattr(loan, 'compute_method') and loan.compute_method:
                    res['compute_method'] = loan.compute_method
        return res

    @api.depends('loan_amount', 'interest_rate', 'loan_term', 'start_date',
                 'first_payment_date', 'payment_end_of_month', 'compute_method')
    def _compute_preview(self):
        for wizard in self:
            if not (wizard.loan_amount and wizard.loan_term and wizard.start_date):
                wizard.preview = ''
                continue

            duration = int(wizard.loan_term * 12) if wizard.loan_term else 12
            rate_annual = (wizard.interest_rate or 0.0) / 100.0
            start_date = wizard.start_date

            # Check active loan
            loan = wizard.loan_id
            active_id = self.env.context.get('active_id') or self.env.context.get('default_loan_id')
            if not loan and active_id:
                loan = self.env['account.loan'].browse(active_id)

            otr = loan.harga_otr if (loan and loan.exists() and loan.harga_otr) else 0.0
            dp = loan.down_payment_leasing if (loan and loan.exists() and loan.down_payment_leasing) else 0.0
            pokok_hutang_awal = otr - dp if (otr > 0 and dp > 0 and otr > dp) else wizard.loan_amount

            cicilan_bulan = loan.monthly_installment if (loan and loan.exists() and loan.monthly_installment) else (loan.installment_amount if (loan and loan.exists()) else 0.0)
            if not cicilan_bulan and duration > 0 and pokok_hutang_awal > 0:
                if rate_annual > 0:
                    bunga_per_bulan = (pokok_hutang_awal * rate_annual) / 12.0
                    pokok_per_bulan = pokok_hutang_awal / duration
                    cicilan_bulan = round(pokok_per_bulan + bunga_per_bulan, 2)
                else:
                    cicilan_bulan = round(pokok_hutang_awal / duration, 2)

            schedule_lines = []
            current_date = start_date

            # Angsuran 1
            pokok_1 = min(pokok_hutang_awal, cicilan_bulan) if cicilan_bulan > 0 else pokok_hutang_awal
            bunga_1 = 0.0
            total_1 = cicilan_bulan
            saldo_pokok_1 = max(0.0, pokok_hutang_awal - pokok_1)
            saldo_pokok_running = saldo_pokok_1

            schedule_lines.append({
                'num': 1,
                'date': current_date,
                'principal': pokok_1,
                'interest': bunga_1,
                'total': total_1,
                'saldo_pokok': saldo_pokok_1,
            })

            # Angsuran 2 to N
            first_payment_date = wizard.first_payment_date
            for i in range(2, duration + 1):
                if i == 2 and first_payment_date:
                    current_date = first_payment_date
                elif first_payment_date:
                    current_date = first_payment_date + relativedelta(months=i-2)
                elif wizard.payment_end_of_month:
                    current_date = start_date + relativedelta(months=i-1, day=31)
                else:
                    current_date = start_date + relativedelta(months=i-1)

                if wizard.compute_method == 'flat':
                    bunga_i = round((saldo_pokok_1 * rate_annual) / 12.0, 2)
                    pokok_i = cicilan_bulan - bunga_i
                else: # 'effective'
                    bunga_i = round(saldo_pokok_running * (rate_annual / 12.0), 2)
                    pokok_i = cicilan_bulan - bunga_i

                total_i = cicilan_bulan
                if i == duration:
                    pokok_i = saldo_pokok_running
                    if wizard.compute_method == 'flat':
                        bunga_i = round((saldo_pokok_1 * rate_annual) / 12.0, 2)
                    else:
                        bunga_i = round(saldo_pokok_running * (rate_annual / 12.0), 2)
                    total_i = pokok_i + bunga_i

                saldo_pokok_running = max(0.0, saldo_pokok_running - pokok_i)

                schedule_lines.append({
                    'num': i,
                    'date': current_date,
                    'principal': pokok_i,
                    'interest': bunga_i,
                    'total': total_i,
                    'saldo_pokok': saldo_pokok_running,
                })

            # Calculate Saldo Bunga
            total_interest = sum(l['interest'] for l in schedule_lines)
            running_interest = total_interest
            for line in schedule_lines:
                running_interest -= line['interest']
                line['saldo_bunga'] = max(0.0, running_interest)

            # Header centered, divider line
            header = (
                f"{'Angs. ke':^8}  "
                f"{'Tanggal':^12}  "
                f"{'Pokok':^15}  "
                f"{'Bunga':^15}  "
                f"{'Total':^15}  "
                f"{'Saldo Pokok':^16}  "
                f"{'Saldo Bunga':^16}\n"
                f"{'-'*8}  {'-'*12}  {'-'*15}  {'-'*15}  {'-'*15}  {'-'*16}  {'-'*16}\n"
            )

            def fmt_money(val, width=12):
                return f"$ {val:>{width},.2f}"

            def row(l):
                d_str = l['date'].strftime('%d/%m/%Y') if l['date'] else ''
                return (
                    f"{l['num']:^8}  "
                    f"{d_str:^12}  "
                    f"{fmt_money(float(l['principal']), 12)}  "
                    f"{fmt_money(float(l['interest']), 12)}  "
                    f"{fmt_money(float(l['total']), 12)}  "
                    f"{fmt_money(float(l['saldo_pokok']), 13)}  "
                    f"{fmt_money(float(l['saldo_bunga']), 13)}\n"
                )

            preview = header
            if len(schedule_lines) <= 10:
                for l in schedule_lines:
                    preview += row(l)
            else:
                for l in schedule_lines[:5]:
                    preview += row(l)
                dots_line = (
                    f"{'. . .':^8}  {'. . .':^12}  "
                    f"{'. . .':^15}  {'. . .':^15}  {'. . .':^15}  "
                    f"{'. . .':^16}  {'. . .':^16}\n"
                )
                preview += dots_line
                for l in schedule_lines[-5:]:
                    preview += row(l)

            wizard.preview = preview

    @api.onchange('compute_method')
    def _onchange_compute_method(self):
        active_id = self.env.context.get('active_id') or self.env.context.get('default_loan_id')
        if active_id:
            loan = self.env['account.loan'].browse(active_id)
            if loan.exists():
                loan.sudo().write({'compute_method': self.compute_method})

    def action_save(self):
        loan_rec = False
        for wizard in self:
            rec = getattr(wizard, 'loan_id', False)
            if not rec or not rec.exists():
                active_id = self.env.context.get('active_id') or self.env.context.get('default_loan_id')
                if active_id:
                    rec = self.env['account.loan'].browse(active_id)
            if rec and rec.exists():
                duration = int(wizard.loan_term * 12) if wizard.loan_term else rec.duration
                rec.write({
                    'compute_method': wizard.compute_method,
                    'interest_rate_annual': wizard.interest_rate,
                    'duration': duration,
                })
                rec.action_compute_amortization_schedule()
                loan_rec = rec
        return {
            'type': 'ir.actions.client',
            'tag': 'reload',
        }

    def action_apply(self):
        return self.action_save()