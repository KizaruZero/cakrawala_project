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
        'account.move', string='Payment Entry', readonly=True, copy=False,
        help="The Journal Entry (Payment) linked to this installment."
    )
    bill_payment_state = fields.Selection(
        related='vendor_bill_id.payment_state',
        string='Payment Status'
    )
    interest_balance = fields.Monetary(
        string = 'Saldo Bunga',
        compute='_compute_interest_balance',
        store=True,
        currency_field='currency_id',
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

    @api.depends('vendor_bill_id.state', 'vendor_bill_id.payment_state')
    def _compute_payment_date(self):
        for line in self:
            # Payment date is explicitly set by the wizard. If not, fallback to move date.
            if line.vendor_bill_id and line.vendor_bill_id.state == 'posted':
                if not line.payment_date:
                    line.payment_date = line.vendor_bill_id.date
            else:
                line.payment_date = False

    @api.depends('vendor_bill_id.state')
    def _compute_is_payment_move_posted(self):
        for line in self:
            line.is_payment_move_posted = line.vendor_bill_id and line.vendor_bill_id.state == 'posted'

    @api.depends('loan_id.line_ids.interest')
    def _compute_interest_balance(self):
        for line in self:
            if not line.loan_id:
                line.interest_balance = 0
                continue
            remaining = line.loan_id.line_ids.filtered(
                lambda l:l.sequence > line.sequence
            )
            line.interest_balance = sum(remaining.mapped('interest'))

    # ---- Action Methods ----

    def action_open_vendor_bill(self):
        """Open the linked Journal Entry (Payment)."""
        self.ensure_one()
        if self.vendor_bill_id:
            return {
                'type': 'ir.actions.act_window',
                'name': _('Payment Entry'),
                'res_model': 'account.move',
                'res_id': self.vendor_bill_id.id,
                'view_mode': 'form',
                'target': 'current',
            }

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
            'partner_id': loan.vendor_id.id if loan.vendor_id else False,
            'line_ids': [
                Command.create({
                    'name': _("Interest Expense"),
                    'account_id': loan.expense_account_id.id,
                    'debit': self.interest,
                    'credit': 0.0,
                    'partner_id': loan.vendor_id.id if loan.vendor_id else False,
                }),
                Command.create({
                    'name': _("Accrued Interest Payable"),
                    'account_id': loan.accrued_interest_account_id.id,
                    'debit': 0.0,
                    'credit': self.interest,
                    'partner_id': loan.vendor_id.id if loan.vendor_id else False,
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
