from markupsafe import Markup

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError
from odoo.tools import format_amount


class RentalCustomerPoPriceWarning(models.TransientModel):
    _name = 'rental.customer.po.price.warning'
    _description = 'Rental Order Customer PO Price Warning'

    order_ids = fields.Many2many('sale.order', required=True, readonly=True)
    comparison_snapshot = fields.Json(required=True, readonly=True)
    comparison_html = fields.Html(compute='_compute_comparison_html')

    @api.depends('comparison_snapshot')
    def _compute_comparison_html(self):
        for wizard in self:
            rows = []
            for values in wizard.comparison_snapshot or []:
                currency = self.env['res.currency'].browse(values['currency_id'])
                po_amount = values['customer_po_amount']
                so_amount = values['amount_total']
                rows.append(Markup(
                    '<tr class="{}"><td>{}</td><td class="text-end">{}</td>'
                    '<td class="text-end">{}</td><td class="text-end">{}</td></tr>'
                ).format(
                    'text-danger' if currency.compare_amounts(po_amount, so_amount) else '',
                    values['order_name'],
                    format_amount(self.env, po_amount, currency),
                    format_amount(self.env, so_amount, currency),
                    format_amount(self.env, so_amount - po_amount, currency),
                ))
            wizard.comparison_html = Markup(
                '<table class="table table-bordered table-sm"><thead><tr>'
                '<th>Rental Order</th><th>Harga PO Customer</th>'
                '<th>Total SO (Termasuk Pajak)</th><th>Selisih (SO - PO)</th>'
                '</tr></thead><tbody>{}</tbody></table>'
            ).format(Markup('').join(rows))

    def _get_action(self):
        self.ensure_one()
        return {
            'name': _('Peringatan Harga PO Customer'),
            'type': 'ir.actions.act_window', 'res_model': self._name,
            'res_id': self.id, 'view_mode': 'form',
            'views': [(self.env.ref('x_sale_purchase_custom.view_customer_po_price_warning_form').id, 'form')],
            'target': 'new',
        }

    def _is_current_for(self, orders):
        self.ensure_one()
        self.check_access('read')
        return (
            self.create_uid == self.env.user
            and set(self.order_ids.ids) == set(orders.ids)
            and self.comparison_snapshot == orders._customer_po_price_warning_snapshot()
        )

    def action_confirm(self):
        self.ensure_one()
        self.check_access('read')
        if self.create_uid != self.env.user:
            raise AccessError(_('Peringatan ini harus dikonfirmasi oleh pengguna yang membukanya. Silakan klik Confirm Order kembali.'))
        orders = self.order_ids.exists()
        orders.check_access('write')
        if not orders or any(order.state not in ('draft', 'sent') for order in orders):
            raise UserError(_('Rental Order sudah dikonfirmasi atau tidak lagi dapat dikonfirmasi. Silakan muat ulang dokumen.'))
        # Re-enter the entire confirmation chain; never bypass other addons,
        # mandatory values, permissions, stock processing or Billing Engine.
        result = orders.with_context(_rental_customer_po_warning_id=self.id).action_confirm()
        return result if isinstance(result, dict) else {'type': 'ir.actions.act_window_close'}
