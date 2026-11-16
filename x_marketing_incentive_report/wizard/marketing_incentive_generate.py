# -*- coding: utf-8 -*-
from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class MarketingIncentiveGenerate(models.TransientModel):
    _name = 'x.marketing.incentive.generate'
    _description = 'Ambil Data Insentif Marketing'

    def _default_date_from(self):
        return fields.Date.context_today(self).replace(day=1)

    def _default_date_to(self):
        return self._default_date_from() + relativedelta(months=1, days=-1)

    date_from = fields.Date(string='Dari Tanggal Live', required=True,
                            default=_default_date_from)
    date_to = fields.Date(string='Sampai Tanggal Live', required=True,
                          default=_default_date_to)
    regenerate = fields.Boolean(
        string='Hitung ulang baris yang sudah ada',
        help='Khusus Manager. Baris periode ini yang sudah pernah diambil '
             'akan ditimpa dengan angka RPC saat ini.',
    )
    is_manager = fields.Boolean(compute='_compute_is_manager')

    @api.depends_context('uid')
    def _compute_is_manager(self):
        is_manager = self.env.user.has_group(
            'x_marketing_incentive_report.group_marketing_incentive_manager')
        for wizard in self:
            wizard.is_manager = is_manager

    def action_generate(self):
        self.ensure_one()
        if self.date_from > self.date_to:
            raise UserError(_('Tanggal awal tidak boleh setelah tanggal akhir.'))
        result = self.env['x.marketing.incentive.line'].generate_for_period(
            self.date_from, self.date_to, regenerate=self.regenerate)
        action = self.env['ir.actions.act_window']._for_xml_id(
            'x_marketing_incentive_report.action_marketing_incentive_line')
        action['domain'] = [
            ('live_date', '>=', self.date_from),
            ('live_date', '<=', self.date_to),
        ]
        action['context'] = {'search_default_group_user': 1}
        action['help'] = _(
            '<p>%(found)s unit ditemukan, %(created)s baris baru, '
            '%(updated)s dihitung ulang.</p>', **result)
        return action
