from odoo import models, fields, api
from odoo.exceptions import ValidationError


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    is_on_risk = fields.Boolean(
        string='On Risk',
        default=False,
        help='Tandai produk ini sebagai produk "On Risk". Hanya 1 produk yang boleh aktif.',
    )

    def _reset_other_on_risk(self, exclude_ids=None):
        exclude_ids = exclude_ids or []
        others = self.sudo().search([
            ('is_on_risk', '=', True),
            ('id', 'not in', exclude_ids),
        ])
        if others:
            others.with_context(skip_on_risk_check=True).write({'is_on_risk': False})

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        new_on_risk = records.filtered(lambda r: r.is_on_risk)
        if new_on_risk:
            self._reset_other_on_risk(exclude_ids=new_on_risk.ids)
        return records

    def write(self, vals):
        result = super().write(vals)
        if self.env.context.get('skip_on_risk_check'):
            return result
        if vals.get('is_on_risk'):
            on_risk_records = self.filtered(lambda r: r.is_on_risk)
            if on_risk_records:
                self._reset_other_on_risk(exclude_ids=on_risk_records.ids)
        return result
