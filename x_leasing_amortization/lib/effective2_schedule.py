"""Declining-balance interest starting with the first installment."""
from decimal import Decimal, localcontext

from dateutil.relativedelta import relativedelta

from .flat_schedule import FlatScheduleError, _decimal, _round


class Effective2ScheduleError(ValueError):
    pass


def build_effective2_schedule(*, principal, annual_rate, months, first_due_date,
                             installment=0, currency_rounding=0.01):
    try:
        with localcontext() as context:
            context.prec = 50
            quantum = _decimal(currency_rounding)
            p, rate, supplied = (_decimal(value) for value in (principal, annual_rate, installment))
            if quantum <= 0:
                raise Effective2ScheduleError('Presisi mata uang harus lebih besar dari nol.')
            p = _round(p, quantum)
            if p <= 0:
                raise Effective2ScheduleError('Total Hutang harus lebih besar dari nol untuk Bunga Efektif 2.')
            if rate < 0 or supplied < 0:
                raise Effective2ScheduleError('Bunga tahunan dan cicilan tidak boleh negatif.')
            if not months or months != int(months) or months < 1:
                raise Effective2ScheduleError('Tenor harus berupa jumlah bulan bulat yang positif.')
            if not first_due_date:
                raise Effective2ScheduleError('Isi Tanggal Jatuh Tempo sebelum Compute.')
            months = int(months)
            monthly_rate = rate / 1200
            # Use the contractual installment; do not silently introduce a
            # different pricing formula when the new method was only asked
            # to change the interest/principal allocation.
            payment = _round(supplied, quantum)
            if payment <= 0:
                raise Effective2ScheduleError('Isi Cicilan Per Bulan atau cicilan kontrak dari PO sebelum Compute Bunga Efektif 2.')
            balance, rows = p, []
            for index in range(months):
                interest = _round(balance * monthly_rate, quantum)
                if index == months - 1:
                    principal_part = balance
                    if months == 1 and supplied and payment != balance + interest:
                        raise Effective2ScheduleError('Untuk satu angsuran, cicilan harus melunasi Total Hutang ditambah bunga bulan pertama.')
                else:
                    principal_part = payment - interest
                    if principal_part < 0:
                        raise Effective2ScheduleError('Cicilan lebih kecil dari bunga bulanan. Periksa Cicilan Per Bulan dan Interest.')
                    if principal_part >= balance:
                        raise Effective2ScheduleError('Cicilan melunasi hutang sebelum akhir tenor. Periksa cicilan atau tenor kontrak.')
                balance -= principal_part
                rows.append({
                    'number': index + 1, 'date': first_due_date + relativedelta(months=index),
                    'principal': principal_part, 'interest': interest,
                    'payment': principal_part + interest, 'outstanding_balance': balance,
                })
            total_interest = sum(row['interest'] for row in rows)
            interest_balance = total_interest
            for row in rows:
                interest_balance -= row['interest']
                row['interest_balance'] = interest_balance
            return {
                'principal': p, 'installment': payment, 'total_interest': total_interest,
                'total_payment': sum(row['payment'] for row in rows), 'rows': rows,
            }
    except FlatScheduleError as error:
        raise Effective2ScheduleError(str(error)) from error
