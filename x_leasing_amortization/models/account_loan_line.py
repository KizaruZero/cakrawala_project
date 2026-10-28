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
    # Related fields for global amortization view
    vendor_id = fields.Many2one('res.partner', related='loan_id.vendor_id', string='Vendor', store=True)
    po_number = fields.Char(related='loan_id.po_number', string='PO Number', store=True)
    start_date_leasing = fields.Date(related='loan_id.start_date_leasing', string='Tanggal Mulai Leasing', store=True)
    vehicle_id = fields.Many2one('fleet.vehicle', related='loan_id.vehicle_id', string='Vehicle', store=True)
    plate_number = fields.Char(related='loan_id.vehicle_id.license_plate', string='Plate Number', store=True)
    remaining_loan = fields.Integer(related='loan_id.remaining_loan', string='Remaining Loan', store=True)

    payment_date = fields.Date(
        string='Payment Date',
        compute='_compute_payment_date',
        store=True,
        readonly=True,
        help='Accounting Date dari jurnal pembayaran yang Posted; bukan tanggal accrued bunga.',
    )
    date_is_manual = fields.Boolean(readonly=True, copy=False)
    vendor_bill_id = fields.Many2one(
        'account.move', string='Payment Entry', readonly=True, copy=False,
        help="The Journal Entry (Payment) linked to this installment."
    )
    bill_payment_state = fields.Selection(
        related='vendor_bill_id.payment_state',
        string='Payment Status'
    )
    journal_state = fields.Selection(
        related='vendor_bill_id.state',
        string='Journal Status',
        store=True,
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

    @api.depends('vendor_bill_id.state', 'vendor_bill_id.date',
                 'generated_move_ids.state', 'generated_move_ids.date',
                 'generated_move_ids.is_loan_payment_move', 'generated_move_ids.reversal_move_ids.state')
    def _compute_payment_date(self):
        for line in self:
            if line.vendor_bill_id and line.vendor_bill_id.state == 'posted':
                line.payment_date = line.vendor_bill_id.date
            else:
                payments = line.generated_move_ids.filtered(lambda move: (
                    move.state == 'posted' and move.is_loan_payment_move
                    and not move.reversal_move_ids.filtered(lambda reversal: reversal.state == 'posted')
                )).sorted(lambda move: (move.date, move.id))
                line.payment_date = payments[-1].date if payments else False

    def write(self, values):
        if 'date' not in values:
            return super().write(values)
        if not values['date']:
            raise UserError(_('Due Date tidak boleh kosong.'))
        loans = self.loan_id.sorted('id')
        with self.env.cr.savepoint():
            previous_order = {}
            refresh = self.env['account.loan']
            refresh_effective2 = self.env['account.loan']
            refresh_import = self.env['account.loan']
            for loan in loans:
                loan._lock_for_early_settlement()
                if loan.state != 'draft' or loan._flat_has_transactions():
                    raise UserError(_('Due Date hanya dapat diedit pada Draft yang belum terhubung transaksi.'))
                previous_order[loan.id] = loan.line_ids.sorted(lambda line: (line.date, line.id)).ids
                if loan.schedule_source == 'import':
                    loan._validate_imported_schedule()
                    refresh_import |= loan
                elif loan.compute_method == 'flat' and loan.schedule_date_policy and loan.flat_schedule_signature:
                    loan._validate_flat_schedule()
                    refresh |= loan
                if loan.compute_method == 'effective_2' and loan.schedule_source != 'import':
                    loan._validate_effective2_schedule()
                    refresh_effective2 |= loan
            result = super().write({**values, 'date_is_manual': True})
            for loan in loans:
                lines = loan.line_ids.sorted(lambda line: (line.date, line.id))
                if (lines.ids != previous_order[loan.id]
                        or len(set(lines.mapped('date'))) != len(lines)):
                    raise UserError(_('Due Date harus tetap berurutan dan tidak boleh sama antar angsuran.'))
            for loan in refresh:
                loan.flat_schedule_signature = loan._flat_fingerprint()
                loan._validate_flat_schedule()
            for loan in refresh_effective2:
                loan.effective2_schedule_signature = loan._effective2_fingerprint()
                loan._validate_effective2_schedule()
            for loan in refresh_import:
                first_date = loan.line_ids.sorted(lambda line: (line.date, line.id))[0].date
                if loan.due_date != first_date:
                    loan.due_date = first_date
                loan._seal_imported_schedule()
            return result

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
