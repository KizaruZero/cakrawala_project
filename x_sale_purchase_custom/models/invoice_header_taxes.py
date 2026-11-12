from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class AccountMove(models.Model):
    _inherit = 'account.move'

    header_tax_ids = fields.Many2many(
        'account.tax', 'account_move_header_tax_rel', 'move_id', 'tax_id',
        string='Taxes', check_company=True, copy=False,
        help='Fill item taxes in one step. Changing this selection replaces the taxes '
             'on all item lines, just like selecting them manually. Line taxes can still be adjusted.',
    )

    def _check_header_taxes(self):
        for move in self:
            if move.move_type not in ('out_invoice', 'in_invoice'):
                if move.header_tax_ids:
                    raise ValidationError(_('Header Taxes is only available on Customer Invoices and Vendor Bills.'))
                # Invisible form/default fields can still send an empty value
                # on journal entries, refunds or receipts. This is not tax input.
                continue
            expected = 'sale' if move.move_type == 'out_invoice' else 'purchase'
            if move.header_tax_ids.filtered(lambda tax: tax.type_tax_use != expected):
                raise ValidationError(_('Select Sales taxes for a Customer Invoice and Purchase taxes for a Vendor Bill.'))

    @api.constrains('header_tax_ids', 'move_type', 'company_id')
    def _constrain_header_taxes(self):
        self.filtered('header_tax_ids')._check_header_taxes()

    def _apply_header_taxes(self):
        self._check_header_taxes()
        invoices = self.filtered(lambda move: move.move_type in ('out_invoice', 'in_invoice'))
        if invoices.filtered(lambda move: move.state != 'draft'):
            raise UserError(_('Header Taxes can only be changed on Draft invoices or bills.'))
        for move in invoices:
            move.invoice_line_ids.filtered(lambda line: line.display_type == 'product').tax_ids = move.header_tax_ids

    @api.onchange('header_tax_ids')
    def _onchange_header_tax_ids(self):
        self.filtered(lambda move: move.state == 'draft' and move.move_type in ('out_invoice', 'in_invoice'))._apply_header_taxes()

    @api.model_create_multi
    def create(self, values_list):
        explicit = ['header_tax_ids' in values for values in values_list]
        moves = super().create(values_list)
        for move, selected in zip(moves, explicit):
            if selected or move.header_tax_ids:
                move._apply_header_taxes()
        return moves

    def write(self, values):
        if 'header_tax_ids' in values:
            invoices = self.filtered(lambda move: (
                move.move_type in ('out_invoice', 'in_invoice')
                or values.get('move_type') in ('out_invoice', 'in_invoice')
            ))
            if invoices and (invoices.filtered(lambda move: move.state != 'draft')
                             or values.get('state', 'draft') != 'draft'):
                raise UserError(_('Header Taxes can only be changed on Draft invoices or bills.'))
            # Validate the final M2M value after write. Empty commands on a
            # Journal Entry must be harmless; real selected taxes still fail
            # the constraint, and invoice/bill tax directions remain enforced.
        result = super().write(values)
        if 'header_tax_ids' in values:
            self._apply_header_taxes()
        return result


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    def _get_computed_taxes(self):
        if (self.display_type == 'product' and self.move_id.state == 'draft'
                and self.move_id.move_type in ('out_invoice', 'in_invoice') and self.move_id.header_tax_ids):
            # Already-selected taxes: do not map fiscal position a second time.
            # Returning the native account.tax recordset leaves all calculations
            # (including PPN, negative PPh and included/grouped taxes) to Odoo.
            return self.move_id.header_tax_ids
        return super()._get_computed_taxes()
