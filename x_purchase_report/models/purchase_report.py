from datetime import datetime
import re

from babel.dates import format_date
from odoo import _, fields, models
from odoo.exceptions import UserError
from odoo.tools.float_utils import float_compare


_RPC_REFERENCE = re.compile(
    r'\bRPC/\d{4}/\d{2}[-/]\d+(?!\w)[ \t]*(?:[-–—:][ \t]*)?',
    re.IGNORECASE,
)


def _po_description_without_rpc(description):
    return '\n'.join(
        paragraph.rstrip() for paragraph in _RPC_REFERENCE.sub('', description or '').splitlines()
        if paragraph.strip()
    ).strip()


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    def _po_report_date(self, value):
        if not value:
            return ''
        if isinstance(value, datetime):
            value = fields.Datetime.context_timestamp(self, value).date()
        return format_date(value, 'dd MMMM yyyy', locale='id_ID')

    def _po_report_lines(self):
        self.ensure_one()
        return self.order_line.filtered(
            lambda line: not line.display_type
            and not line.is_downpayment
            and line.product_qty != 0
            and (line.product_id.name or '').strip().casefold() != 'down payment'
        )

    def _po_report_rows(self):
        """Input Order controls the rows; its generated units supply actual money.

        Never regroup by product: two Input Order rows of the same variant can
        have different commercial conditions. Never write to purchase lines.
        """
        self.ensure_one()
        if not self.input_line_ids:
            raise UserError(_(
                'Purchase Order %s has no Input Order lines. This printout only '
                'uses Input Order; Products are not used as a fallback.', self.name,
            ))
        rows = []
        for source in self.input_line_ids.sorted(lambda item: (item.sequence, item.id)):
            lines = source.generated_line_ids.filtered(
                lambda line: not line.display_type and not line.is_downpayment
                and line.product_qty != 0
            )
            uom = source.product_uom_id or source.product_id.uom_id
            if source.quantity <= 0 or not lines or float_compare(
                sum(lines.mapped('product_qty')), source.quantity,
                precision_rounding=uom.rounding,
            ):
                raise UserError(_(
                    'Generate all Order Lines for Input Order "%s" on %s before '
                    'printing. Printed quantities must match the generated units '
                    'whose discounts and taxes are included.', source.product_id.display_name, self.name,
                ))
            if any(line.order_id != self or line.product_id != source.product_id or line.product_uom_id != uom for line in lines):
                raise UserError(_(
                    'The generated order/product/unit does not match Input Order "%s" '
                    'on %s. Review those lines before printing.', source.product_id.display_name, self.name,
                ))
            # The generated lines may have acquired the vendor's actual price
            # after Input Order was entered. Their weighted gross unit price
            # preserves the same commercial values as the PO, including such cases.
            gross = sum(line.price_unit * line.product_qty for line in lines)
            fixed_discount = sum(
                line.fixed_discount or line.price_unit * line.product_qty * line.discount / 100
                for line in lines
            )
            product_name = _po_description_without_rpc(source.product_id.display_name)
            description = _po_description_without_rpc(source.name)
            rows.append({
                'input_line_id': source.id,
                'product_name': product_name,
                'description': description if description != product_name else '',
                'quantity': source.quantity,
                'uom_name': uom.name,
                'price_unit': gross / source.quantity,
                'fixed_discount': fixed_discount,
                'amount': sum(lines.mapped('price_total')),
            })
        return rows

    def action_print_custom(self):
        if not self:
            raise UserError("No record selected to print.")

        report = self.env.ref('x_purchase_report.report_purchase_order_custom_action')
        if not report:
            raise UserError("Custom report not found. Please check module.")
        
        return report.report_action(self)


class PurchaseOrderCustomReport(models.AbstractModel):
    _name = 'report.x_purchase_report.report_purchase_order_custom'
    _description = 'Purchase Order Printout from Input Order'

    def _get_report_values(self, docids, data=None):
        docs = self.env['purchase.order'].browse(docids)
        docs.check_access('read')
        rows = {order.id: order._po_report_rows() for order in docs}
        return {
            'doc_ids': docs.ids,
            'doc_model': 'purchase.order',
            'docs': docs,
            'po_report_rows': rows,
            # Non-input charges/rounding are disclosed in totals, never silently
            # hidden or printed as product rows. The actual PO total is untouched.
            'po_report_other_amounts': {
                order.id: order.currency_id.round(
                    order.amount_total - sum(row['amount'] for row in rows[order.id])
                ) for order in docs
            },
        }
