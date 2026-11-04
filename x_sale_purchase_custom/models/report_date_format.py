"""Print-outs show dates as 02-November-2026; the web client keeps the language format.

res.lang.date_format only offers numeric patterns, and changing it would also affect
every form and list. Only the report render path sets the context key, so mail templates
and backend views are untouched. An explicit `format` option in a template still wins.
"""
from odoo import api, models
from odoo.tools import posix_to_ldml
from odoo.tools.misc import babel_locale_parse


PRINT_DATE_FORMAT = 'dd-MMMM-yyyy'
_PRINT_CONTEXT_KEY = 'x_print_date_format'
# These print-outs keep the language date format.
_LANGUAGE_FORMAT_REPORTS = {
    'account_payment_order.print_account_payment_order_main',
    'payment_receive_voucher.report_payment_voucher_document',
    'payment_receive_voucher.report_payment_voucher_summary',
    'x_po_report.report_po_custom',
    'x_rental_profit_calculation.report_rpc_summary_document',
    'x_sale_purchase_custom.report_pks_payung_template',
    'x_vehicle_pnl_report.report_vehicle_pnl_document',
}


class IrActionsReport(models.Model):
    _inherit = 'ir.actions.report'

    def _render_template(self, template, values=None):
        if template in _LANGUAGE_FORMAT_REPORTS:
            return super()._render_template(template, values)
        report = self.with_context(**{_PRINT_CONTEXT_KEY: True})
        return super(IrActionsReport, report)._render_template(template, values)


class IrQwebFieldDate(models.AbstractModel):
    _inherit = 'ir.qweb.field.date'

    @api.model
    def value_to_html(self, value, options):
        if self.env.context.get(_PRINT_CONTEXT_KEY) and not options.get('format'):
            options = dict(options, format=PRINT_DATE_FORMAT)
        return super().value_to_html(value, options)


class IrQwebFieldDatetime(models.AbstractModel):
    _inherit = 'ir.qweb.field.datetime'

    @api.model
    def value_to_html(self, value, options):
        if (self.env.context.get(_PRINT_CONTEXT_KEY)
                and 'format' not in options and not options.get('time_only')):
            pattern = PRINT_DATE_FORMAT
            if not options.get('date_only'):
                lang = self.user_lang()
                time_pattern = posix_to_ldml(lang.time_format, locale=babel_locale_parse(lang.code))
                pattern = '%s %s' % (pattern, time_pattern)
            options = dict(options, format=pattern)
        return super().value_to_html(value, options)
