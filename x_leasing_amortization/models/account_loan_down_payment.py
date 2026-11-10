from math import isfinite

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError, UserError


_INPUTS = {'harga_otr', 'down_payment_leasing', 'down_payment_type', 'down_payment_percentage'}


class AccountLoan(models.Model):
    _inherit = 'account.loan'

    down_payment_type = fields.Selection(
        [('fixed', 'Fixed Amount'), ('percentage', 'Percentage (%)')],
        string='Down Payment Type', default='fixed', required=True, tracking=True,
    )
    down_payment_percentage = fields.Float(
        string='Down Payment (%)', digits=(16, 6), tracking=True,
        help='Enter 10 for 10%. The monetary Down Payment is calculated from Harga OTR.',
    )

    def _uses_down_payment_formula(self):
        self.ensure_one()
        # The existing conversion policy identifies current Compute contracts.
        # Do not recalculate historical policies or imported principal on upgrade.
        return self.schedule_source != 'import' and self.use_rate_conversion

    def _down_payment_values(self, values):
        self.ensure_one()
        currency = self.currency_id
        otr = values.get('harga_otr', self.harga_otr)
        kind = values.get('down_payment_type', self.down_payment_type) or 'fixed'
        percent = values.get('down_payment_percentage', self.down_payment_percentage)
        dp = values.get('down_payment_leasing', self.down_payment_leasing)
        try:
            otr, percent, dp = (float(value or 0) for value in (otr, percent, dp))
        except (TypeError, ValueError) as error:
            raise ValidationError(_('Harga OTR dan Down Payment harus berupa angka.')) from error
        if not isfinite(percent) or not 0 <= percent <= 100:
            raise ValidationError(_('Down Payment (%) harus antara 0 dan 100.'))
        if not isfinite(otr) or otr < 0 or not isfinite(dp) or dp < 0:
            raise ValidationError(_('Harga OTR dan Down Payment harus angka valid yang tidak negatif.'))
        otr = currency.round(otr)
        if kind == 'percentage':
            dp = currency.round(otr * percent / 100)
        else:
            dp = currency.round(dp)
        if dp > otr:
            raise ValidationError(_('Down Payment tidak boleh melebihi Harga OTR.'))
        return {'down_payment_leasing': dp, 'total_hutang': currency.round(otr - dp),
                'amount_borrowed': currency.round(otr - dp)}

    @api.onchange('harga_otr', 'down_payment_type', 'down_payment_percentage', 'down_payment_leasing')
    def _onchange_down_payment_input(self):
        for loan in self:
            if loan._uses_down_payment_formula():
                loan.update(loan._down_payment_values({}))

    @api.model_create_multi
    def create(self, values_list):
        loans = super().create(values_list)
        # Resolve PO-computed OTR/DP first, then synchronize each unit's principal.
        for loan, supplied in zip(loans, values_list):
            if not loan._uses_down_payment_formula():
                continue
            # These fields share the legacy PO compute. Reading a missing DP
            # can initialize that compute; retain explicitly supplied OTR/DP.
            values = {name: supplied[name] for name in _INPUTS.intersection(supplied)}
            values.update(loan._down_payment_values(values))
            if any(loan[name] != value for name, value in values.items()):
                loan.write(values)
        return loans

    def write(self, values):
        if _INPUTS.intersection(values):
            for loan in self:
                changed = any(loan[name] != loan._fields[name].convert_to_cache(values[name], loan)
                              for name in _INPUTS.intersection(values))
                if changed and (loan.state != 'draft' or loan._flat_has_transactions()):
                    raise UserError(_('Down Payment dan Harga OTR hanya dapat diubah pada Draft tanpa transaksi.'))
        if _INPUTS.intersection(values) or {'total_hutang', 'amount_borrowed', 'use_rate_conversion'}.intersection(values):
            result = True
            for loan in self:
                prepared = dict(values)
                if loan._uses_down_payment_formula() or (
                    values.get('use_rate_conversion') and loan.schedule_source != 'import'
                ):
                    prepared.update(loan._down_payment_values(prepared))
                result = super(AccountLoan, loan).write(prepared) and result
            return result
        return super().write(values)

    @api.constrains('harga_otr', 'down_payment_type', 'down_payment_percentage', 'down_payment_leasing',
                    'use_rate_conversion', 'total_hutang')
    def _check_down_payment_input(self):
        for loan in self.filtered(lambda item: item._uses_down_payment_formula() or item.schedule_source == 'import'):
            if (not isfinite(loan.down_payment_percentage)
                    or not 0 <= loan.down_payment_percentage <= 100):
                raise ValidationError(_('Down Payment (%) harus antara 0 dan 100.'))
            if (any(not isfinite(value) or value < 0 for value in (loan.harga_otr, loan.down_payment_leasing))
                    or loan.down_payment_leasing > loan.harga_otr):
                raise ValidationError(_('Down Payment harus tidak negatif dan tidak melebihi Harga OTR.'))
            if loan.schedule_source == 'import':
                if loan.down_payment_type != 'fixed':
                    raise ValidationError(_('Down Payment pada file impor harus berupa nominal tetap.'))
                if not loan.currency_id.is_zero(loan.total_hutang - (loan.harga_otr - loan.down_payment_leasing)):
                    raise ValidationError(_('Total Hutang impor harus sama dengan Harga OTR dikurangi Down Payment.'))
