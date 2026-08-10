# -*- coding: utf-8 -*-
from odoo import api, fields, models, _, Command
from odoo.exceptions import UserError


class AccountLoanLine(models.Model):
    """Extend account.loan.line with payment date tracking and vendor bill link."""
    _inherit = 'account.loan.line'

    # ---- Custom Fields ----
    installment_number = fields.Integer(
        string='No. Angsuran',
        compute='_compute_installment_number',
        store=True,
        help='Sequential installment number (1, 2, 3, ...).',
    )
    payment_date = fields.Date(
        string='Tanggal Bayar',
        compute='_compute_payment_date',
        store=True,
        help='Payment date — empty when schedule is created, filled when payment is posted.',
    )
    vendor_bill_id = fields.Many2one(
        'account.move',
        string='Vendor Bill',
        readonly=True,
        copy=False,
        help='The vendor bill generated for this installment.',
    )
    bill_payment_state = fields.Selection(
        string='Bill Status',
        related='vendor_bill_id.payment_state',
        readonly=True,
    )

    # ---- Compute Methods ----

    @api.depends('loan_id.line_ids', 'date')
    def _compute_installment_number(self):
        for line in self:
            if line.loan_id and line.date:
                sorted_lines = line.loan_id.line_ids.sorted('date')
                for idx, l in enumerate(sorted_lines, start=1):
                    if l.id == line.id:
                        line.installment_number = idx
                        break
                else:
                    line.installment_number = 0
            else:
                line.installment_number = 0

    @api.depends('vendor_bill_id.payment_state')
    def _compute_payment_date(self):
        for line in self:
            if line.vendor_bill_id and line.vendor_bill_id.payment_state in ('in_payment', 'paid'):
                payments = line.vendor_bill_id._get_reconciled_payments()
                if payments:
                    line.payment_date = max(payments.mapped('date'))
                else:
                    line.payment_date = line.vendor_bill_id.date
            else:
                line.payment_date = False

    @api.depends('vendor_bill_id.payment_state')
    def _compute_is_payment_move_posted(self):
        for line in self:
            line.is_payment_move_posted = line.vendor_bill_id and line.vendor_bill_id.payment_state in ('in_payment', 'paid')

    # ---- Action Methods ----

    def action_generate_vendor_bill(self):
        """Generate a vendor bill for this specific loan line."""
        self.ensure_one()
        bill = self._generate_vendor_bill()
        if bill:
            return {
                'type': 'ir.actions.act_window',
                'name': _('Vendor Bill'),
                'res_model': 'account.move',
                'res_id': bill.id,
                'view_mode': 'form',
                'target': 'current',
            }

    def _generate_vendor_bill(self):
        """Create a vendor bill (in_invoice) for this loan line.

        Returns the created account.move record, or False if already billed.
        """
        self.ensure_one()
        if self.vendor_bill_id:
            raise UserError(_(
                "A vendor bill already exists for installment #%s (Bill: %s).",
                self.installment_number, self.vendor_bill_id.name,
            ))

        loan = self.loan_id
        if loan.skip_until_date and self.date <= loan.skip_until_date:
            raise UserError(_(
                "Cannot generate vendor bill for installment #%s. "
                "This installment falls on or before the 'Skip until' date (%s), "
                "meaning it has already been billed (e.g. via Down Payment Invoice).",
                self.installment_number, loan.skip_until_date,
            ))

        # Determine partner: use leasing partner from PO if available, else bank
        partner = False
        if loan.purchase_order_id and hasattr(loan.purchase_order_id, 'leasing_partner_id') and loan.purchase_order_id.leasing_partner_id:
            partner = loan.purchase_order_id.leasing_partner_id
        elif loan.bank_id:
            partner = loan.bank_id
        elif loan.vendor_id:
            partner = loan.vendor_id

        if not partner:
            raise UserError(_(
                "Cannot generate vendor bill: no Leasing Partner, Bank, or Vendor configured on this loan."
            ))

        # Build invoice line values
        invoice_line_vals = []

        # Principal line
        if self.principal:
            invoice_line_vals.append(Command.create({
                'name': _("%s - Principal #%s (%s)", loan.name, self.installment_number, self.date),
                'quantity': 1,
                'price_unit': self.principal,
                'account_id': loan.long_term_account_id.id if loan.long_term_account_id else False,
            }))

        # Interest line (BIAYA BUNGA YMH DIBAYAR)
        if self.interest:
            accrued_acc = loan.accrued_interest_account_id or loan.expense_account_id
            invoice_line_vals.append(Command.create({
                'name': _("%s - Interest #%s (%s)", loan.name, self.installment_number, self.date),
                'quantity': 1,
                'price_unit': self.interest,
                'account_id': accrued_acc.id if accrued_acc else False,
            }))

        bill_vals = {
            'move_type': 'in_invoice',
            'partner_id': partner.id,
            'invoice_date': self.date,
            'date': self.date,
            'ref': _("%s - Installment #%s", loan.name, self.installment_number),
            'invoice_line_ids': invoice_line_vals,
        }

        # Link to PO if available
        if loan.purchase_order_id:
            bill_vals['invoice_origin'] = loan.purchase_order_id.name

        bill = self.env['account.move'].sudo().create(bill_vals)
        self.vendor_bill_id = bill.id

        return bill

    monthly_adjustment_move_id = fields.Many2one(
        'account.move', string='Monthly Adjustment Entry', readonly=True, copy=False,
        help="The monthly journal entry that accrues interest (Dr. Expense, Cr. Accrued Liability)"
    )

    @api.model
    def _cron_generate_interest_adjustment(self):
        """Cron job to automatically generate Monthly Interest Adjustment Journal Entry."""
        today = fields.Date.context_today(self)
        lines = self.search([
            ('date', '<=', today),
            ('interest', '>', 0),
            ('monthly_adjustment_move_id', '=', False),
            ('loan_id.state', '=', 'running'),
        ])
        for line in lines:
            line._generate_monthly_adjustment_entry()

    def _generate_monthly_adjustment_entry(self):
        self.ensure_one()
        if self.monthly_adjustment_move_id:
            return self.monthly_adjustment_move_id
            
        loan = self.loan_id
        if loan.skip_until_date and self.date <= loan.skip_until_date:
            return False
            
        if not loan.expense_account_id or not loan.accrued_interest_account_id:
            return False
            
        move_vals = {
            'move_type': 'entry',
            'date': self.date,
            'ref': _("Accrued Interest - %s - Installment #%s", loan.name, self.installment_number),
            'journal_id': loan.journal_id.id,
            'line_ids': [
                Command.create({
                    'name': _("Interest Expense"),
                    'account_id': loan.expense_account_id.id,
                    'debit': self.interest,
                    'credit': 0.0,
                }),
                Command.create({
                    'name': _("Accrued Interest Payable"),
                    'account_id': loan.accrued_interest_account_id.id,
                    'debit': 0.0,
                    'credit': self.interest,
                }),
            ]
        }
        move = self.env['account.move'].sudo().create(move_vals)
        move.action_post()
        self.monthly_adjustment_move_id = move.id
        return move

    def action_open_vendor_bill(self):
        """Open the related vendor bill."""
        self.ensure_one()
        if not self.vendor_bill_id:
            raise UserError(_("No vendor bill has been generated for this installment yet."))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Vendor Bill'),
            'res_model': 'account.move',
            'res_id': self.vendor_bill_id.id,
            'view_mode': 'form',
            'target': 'current',
        }
