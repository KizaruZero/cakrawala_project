"""Flat contract pricing with equivalent annuity allocation (no ORM writes)."""
from decimal import Decimal, ROUND_HALF_UP, localcontext

from dateutil.relativedelta import relativedelta


class FlatScheduleError(ValueError):
    pass


def _decimal(value):
    try:
        result = Decimal(str(value or 0))
    except Exception as error:
        raise FlatScheduleError('Nilai pembiayaan/cicilan/bunga tidak valid.') from error
    if not result.is_finite():
        raise FlatScheduleError('Nilai pembiayaan/cicilan/bunga harus berupa angka finite.')
    return result


def _round(value, quantum):
    return (value / quantum).quantize(Decimal(1), rounding=ROUND_HALF_UP) * quantum


def _monthly_rate(principal, payment, months, advance):
    """Equivalent to RATE(months, -payment, principal, 0, advance)."""
    def present_value(rate):
        value = payment * (1 - (1 + rate) ** (-months)) / rate
        return value * (1 + rate) if advance else value

    low, high = Decimal(0), Decimal('0.01')
    for _ in range(80):
        if present_value(high) <= principal:
            break
        high *= 2
    else:
        raise FlatScheduleError('Rate ekuivalen tidak dapat ditemukan. Periksa cicilan dan tenor.')
    for _ in range(140):
        middle = (low + high) / 2
        if present_value(middle) > principal:
            low = middle
        else:
            high = middle
    return (low + high) / 2


def build_flat_schedule(*, principal, annual_flat_rate, months, start_date,
                        advance, installment=0, currency_rounding=0.01,
                        interest_rounding=1, payment_timing='anniversary'):
    """A contract installment wins over the quoted flat rate when supplied.

    ADDM pays at t=0; arrears pays at t=1. Ordinary rounded interest is allocated
    from the equivalent monthly rate, with the final interest residual keeping
    the contract installment and both ending balances exact. Zero-rate rounding
    differences instead adjust the final principal-only payment.
    """
    with localcontext() as context:
        context.prec = 50
        quantum = _decimal(currency_rounding)
        interest_quantum = _decimal(interest_rounding)
        p, rate = _decimal(principal), _decimal(annual_flat_rate)
        if quantum <= 0 or interest_quantum <= 0:
            raise FlatScheduleError('Presisi pembulatan harus lebih besar dari nol.')
        p = _round(p, quantum)
        if p <= 0:
            raise FlatScheduleError('Pokok pembiayaan harus lebih besar dari nol.')
        if rate < 0:
            raise FlatScheduleError('Bunga flat tahunan tidak boleh negatif.')
        if not months or months != int(months) or months < 1:
            raise FlatScheduleError('Tenor harus berupa jumlah bulan bulat yang positif.')
        months = int(months)
        if not start_date:
            raise FlatScheduleError('Leasing Start Date harus diisi untuk Bunga Flat.')
        if payment_timing not in ('anniversary', 'end_of_month'):
            raise FlatScheduleError('Pilihan tanggal angsuran Flat tidak valid.')
        manual = _decimal(installment)
        if manual < 0:
            raise FlatScheduleError('Cicilan kontrak tidak boleh negatif.')
        automatic = not bool(manual)
        payment = _round(manual or (p / months + p * rate / 1200), quantum)
        if advance and months == 1:
            if manual and payment != p:
                raise FlatScheduleError('ADDM satu angsuran harus sama dengan pokok, tanpa bunga.')
            payment = p
        if payment <= 0:
            raise FlatScheduleError('Cicilan harus lebih besar dari nol.')
        contract_interest = payment * months - p
        tolerance = quantum * months / 2
        if contract_interest < -tolerance:
            raise FlatScheduleError('Cicilan dikali tenor lebih kecil dari pokok pembiayaan.')
        if advance and months > 1 and payment >= p:
            raise FlatScheduleError('Cicilan ADDM harus lebih kecil dari pokok untuk tenor lebih dari satu bulan.')
        zero_rate = abs(contract_interest) <= tolerance
        monthly = Decimal(0) if zero_rate else _monthly_rate(p, payment, months, advance)
        budget = Decimal(0) if zero_rate else contract_interest
        balance = p
        rows = []
        for index in range(months):
            offset = index if advance else index + 1
            due_date = start_date + relativedelta(months=offset)
            if payment_timing == 'end_of_month' and not (advance and index == 0):
                due_date += relativedelta(day=31)
            if advance and index == 0:
                interest = Decimal(0)
            elif index == months - 1:
                interest = budget
            else:
                interest = min(_round(balance * monthly, interest_quantum), budget)
            principal_part = balance if index == months - 1 else payment - interest
            if principal_part < 0 or principal_part > balance:
                raise FlatScheduleError('Pembulatan bunga tidak sesuai cicilan. Gunakan Presisi Mata Uang atau periksa kontrak.')
            balance -= principal_part
            budget -= interest
            rows.append({
                'number': index + 1, 'date': due_date,
                'principal': principal_part, 'interest': interest,
                'payment': principal_part + interest,
                'outstanding_balance': balance, 'interest_balance': budget,
            })
        total_interest = sum(row['interest'] for row in rows)
        return {
            'principal': p, 'installment': payment, 'automatic': automatic,
            'monthly_rate': monthly,
            'effective_annual_percent': monthly * 1200,
            'implied_flat_annual_percent': total_interest / p * 1200 / months,
            'total_interest': total_interest,
            'total_payment': sum(row['payment'] for row in rows),
            'rows': rows,
        }
