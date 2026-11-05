from datetime import datetime
import re

from babel.dates import format_date
from odoo import _, api, fields, models
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

    po_contact_id = fields.Many2one(
        'res.partner', string='UP', check_company=True, tracking=True,
        domain="[('is_company', '=', False), ('company_id', 'in', [False, company_id])]",
        help='Pilih PIC/penerima dari Contact untuk dicetak pada Shipping Address PO ini.')
    po_contact_mobile = fields.Char(
        string='No. HP', tracking=True,
        help='Disalin dari Mobile/Phone Contact saat UP dipilih; dapat diedit khusus pada PO ini.')

    @api.constrains('po_contact_id', 'company_id')
    def _check_po_contact_company(self):
        # Purchase does not enable automatic company checks on every field.
        # Check only this new relation without changing legacy PO validations.
        self._check_company(['po_contact_id'])

    def _po_contact_phone(self, contact_id):
        contact = self.env['res.partner'].browse(contact_id).exists()
        if contact:
            contact.check_access('read')
        # Odoo 19 standard Contacts has Phone; some databases also retain Mobile.
        return getattr(contact, 'mobile', False) or contact.phone or False

    @api.onchange('po_contact_id')
    def _onchange_po_contact_id(self):
        for order in self:
            order.po_contact_mobile = getattr(order.po_contact_id, 'mobile', False) or order.po_contact_id.phone or False

    @api.model_create_multi
    def create(self, values_list):
        prepared = []
        for values in values_list:
            values = dict(values)
            if 'po_contact_id' in values and 'po_contact_mobile' not in values:
                values['po_contact_mobile'] = self._po_contact_phone(values['po_contact_id'])
            prepared.append(values)
        return super().create(prepared)

    def write(self, values):
        if 'po_contact_id' in values and 'po_contact_mobile' not in values:
            values = {**values, 'po_contact_mobile': self._po_contact_phone(values['po_contact_id'])}
        return super().write(values)

    def _po_report_tax_labels(self, lines):
        """Actual generated PO taxes, deduplicated for a grouped Input row."""
        taxes = lines.tax_ids.sorted(lambda tax: (tax.sequence, tax.id))
        return ', '.join(dict.fromkeys(tax.tax_label or tax.name for tax in taxes))

    def _po_report_date(self, value):
        if not value:
            return ''
        if isinstance(value, datetime):
            value = fields.Datetime.context_timestamp(self, value).date()
        return format_date(value, 'dd-MMMM-yyyy', locale='en_US')

    def _po_report_lines(self):
        self.ensure_one()
        return self.order_line.filtered(
            lambda line: not line.display_type
            and not line.is_downpayment
            and line.product_qty != 0
            and (line.product_id.name or '').strip().casefold() != 'down payment'
        )

    def _po_report_rows(self):
        """Prefer populated Input Order; otherwise print the Products lines.

        Never regroup by product: two Input Order rows of the same variant can
        have different commercial conditions. Never write to purchase lines.
        """
        self.ensure_one()
        input_lines = self.input_line_ids if 'input_line_ids' in self._fields else False
        if not input_lines:
            return self._po_report_product_rows()
        rows = []
        for source in input_lines.sorted(lambda item: (item.sequence, item.id)):
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
                'taxes': self._po_report_tax_labels(lines),
            })
        return rows

    def _po_report_product_rows(self):
        """Products fallback for legacy/SPK POs or an empty Input Order tab."""
        self.ensure_one()
        rows = []
        for line in self._po_report_lines().sorted(lambda item: (item.sequence, item.id)):
            product_name = _po_description_without_rpc(line.product_id.display_name)
            description = _po_description_without_rpc(line.name)
            rows.append({
                'input_line_id': False,
                'purchase_line_id': line.id,
                'product_name': product_name,
                'description': description if description != product_name else '',
                'quantity': line.product_qty,
                'uom_name': line.product_uom_id.name,
                'price_unit': line.price_unit,
                'fixed_discount': (
                    line.fixed_discount
                    or line.price_unit * line.product_qty * line.discount / 100
                ),
                'amount': line.price_total,
                'taxes': self._po_report_tax_labels(line),
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
    _description = 'Purchase Order Printout from Input Order or Products'

    def _get_report_values(self, docids, data=None):
        docs = self.env['purchase.order'].browse(docids)
        docs.check_access('read')
        rows = {order.id: order._po_report_rows() for order in docs}
        return {
            'doc_ids': docs.ids,
            'doc_model': 'purchase.order',
            'docs': docs,
            'po_report_rows': rows,
            # Amounts outside the selected item rows are disclosed in totals,
            # not silently hidden. The actual PO total is untouched.
            'po_report_other_amounts': {
                order.id: order.currency_id.round(
                    order.amount_total - sum(row['amount'] for row in rows[order.id])
                ) for order in docs
            },
        }
