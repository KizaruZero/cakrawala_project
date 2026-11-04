"""Flat quotes / monthly annuities, with Excel RATE(type=1) ADDM allocation.

Rates are annual percentage points (5.5 means 5.5%). The effective quote is
12 times the monthly rate, not a compounded annual yield. No ORM side effects.
"""
from decimal import Decimal, DecimalException, InvalidOperation, ROUND_HALF_UP, localcontext

from dateutil.relativedelta import relativedelta


class InterestConversionError(ValueError):
    pass


def _number(value):
    try:
        value = Decimal(str(value or 0))
        if not value.is_finite():
            raise ValueError()
        return value
    except (InvalidOperation, ValueError, TypeError) as error:
        raise InterestConversionError('Parameter bunga/cicilan harus berupa angka yang valid.') from error


def _round(value, quantum):
    try:
        return (value / quantum).quantize(Decimal(1), rounding=ROUND_HALF_UP) * quantum
    except DecimalException as error:
        raise InterestConversionError('Nominal terlalu besar untuk presisi perhitungan mata uang.') from error


def _payment(principal, monthly_rate, months, advance):
    if not monthly_rate:
        return principal / months
    return principal * monthly_rate / (1 - (1 + monthly_rate) ** -months) / (
        1 + monthly_rate if advance else 1)


def _rate(principal, payment, months, advance):
    """Nonnegative RATE equivalent using a monotone PV bisection."""
    if payment * months == principal:
        return Decimal(0)
    if payment * months < principal or (advance and payment >= principal):
        raise InterestConversionError('Cicilan tidak dapat dikonversi menjadi bunga efektif nonnegatif untuk tenor ini.')

    def pv(rate):
        return payment * (1 - (1 + rate) ** -months) / rate * (1 + rate if advance else 1)

    low, high = Decimal(0), Decimal(1)
    for _ in range(40):
        if pv(high) <= principal:
            break
        high *= 2
    else:
        raise InterestConversionError('Bunga efektif tidak dapat ditemukan. Periksa pokok, tenor dan cicilan kontrak.')
    for _ in range(180):
        middle = (low + high) / 2
        if pv(middle) > principal:
            low = middle
        else:
            high = middle
    return (low + high) / 2


def quote_interest(*, principal, months, input_type, annual_rate, advance,
                   installment=0, currency_rounding=0.01):
    with localcontext() as context:
        context.prec = 60
        p, rate, contract, quantum = map(_number, (principal, annual_rate, installment, currency_rounding))
        n = _number(months)
        if quantum <= 0 or p <= 0 or rate < 0 or contract < 0:
            raise InterestConversionError('Pokok/presisi harus positif; bunga dan cicilan tidak boleh negatif.')
        if n != int(n) or not 1 <= n <= 1200:
            raise InterestConversionError('Tenor harus bilangan bulat antara 1 dan 1200 bulan.')
        n = int(n)
        if input_type not in ('flat', 'effective') or not isinstance(advance, bool):
            raise InterestConversionError('Pilih Jenis Input Bunga dan Advarr terlebih dahulu.')
        p = _round(p, quantum)
        if not p:
            raise InterestConversionError('Total Hutang harus lebih besar dari nol setelah pembulatan.')
        if advance and n == 1 and (rate or (contract and _round(contract, quantum) != p)):
            raise InterestConversionError('ADDM satu angsuran harus sama dengan pokok tanpa bunga; konversi bunga tidak terdefinisi.')
        theoretical = (p / n + p * rate / 1200 if input_type == 'flat'
                       else _payment(p, rate / 1200, n, advance))
        automatic_payment = _round(theoretical, quantum)
        payment = _round(contract, quantum) if contract else automatic_payment
        if payment <= 0:
            raise InterestConversionError('Cicilan harus lebih besar dari nol.')
        interest = payment * n - p
        # Zero-rate installment rounding may make N*C lower than principal by
        # a few cents. Only that currency-rounding residual goes to the last row.
        if interest < 0:
            if abs(interest) > quantum * n / 2:
                raise InterestConversionError('Cicilan dikali tenor lebih kecil dari Total Hutang.')
            interest = Decimal(0)
        effective = (_rate(p, payment, n, advance) if interest else Decimal(0))
        return {
            'principal': p, 'months': n, 'installment': payment, 'automatic': not bool(contract),
            'automatic_installment': automatic_payment, 'total_interest': interest,
            'flat_rate': interest / p * 1200 / n,
            'effective_rate': effective * 1200, 'monthly_rate': effective,
            'contract_mismatch': bool(contract and payment != automatic_payment),
        }


def build_converted_schedule(*, first_due_date, interest_rounding=0.01, **settings):
    with localcontext() as context:
        context.prec = 60
        if not first_due_date:
            raise InterestConversionError('Isi Tanggal Jatuh Tempo sebelum Compute jadwal angsuran.')
        result = quote_interest(**settings)
        quantum = _number(settings.get('currency_rounding', 0.01))
        interest_quantum = _number(interest_rounding)
        if interest_quantum < quantum or interest_quantum % quantum:
            raise InterestConversionError('Presisi pembulatan bunga harus sesuai presisi mata uang.')
        balance, budget = result['principal'], result['total_interest']
        rows = []
        for index in range(result['months']):
            last = index == result['months'] - 1
            if settings['advance'] and index == 0:
                interest = Decimal(0)
            elif last:
                interest = budget
            else:
                interest = min(_round(balance * result['monthly_rate'], interest_quantum), budget)
            principal = balance if last else result['installment'] - interest
            if principal < 0 or principal > balance:
                raise InterestConversionError('Pembulatan tidak sesuai cicilan. Gunakan Presisi Mata Uang atau periksa kontrak.')
            balance -= principal
            budget -= interest
            rows.append({
                'number': index + 1, 'date': first_due_date + relativedelta(months=index),
                'principal': principal, 'interest': interest, 'payment': principal + interest,
                'outstanding_balance': balance, 'interest_balance': budget,
            })
        return {**result, 'rows': rows, 'total_payment': sum(row['payment'] for row in rows)}
