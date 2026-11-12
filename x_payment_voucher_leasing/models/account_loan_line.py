# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.tools import SQL


class AccountLoanLine(models.Model):
    _inherit = 'account.loan.line'

    leasing_voucher_id = fields.Many2one(
        'leasing.payment.voucher',
        string='Payment Voucher Leasing',
        readonly=True,
        copy=False,
        index=True,
    )
    leasing_voucher_state = fields.Selection(
        related='leasing_voucher_id.state',
        string='Voucher Status',
        readonly=True,
        store=True,
    )

    def _lock_leasing_voucher_sources(self):
        """Keep PO payment recipients stable and serialize installment payments."""
        self.check_access('write')
        orders = self.loan_id.purchase_order_id.sorted('id')
        if orders:
            orders.flush_recordset(['leasing_partner_id'])
            self.env.cr.execute(SQL(
                'SELECT id FROM purchase_order WHERE id IN %s ORDER BY id FOR SHARE',
                tuple(orders.ids),
            ))
            orders.invalidate_recordset(['leasing_partner_id'])
        for loan in self.loan_id.sorted('id'):
            loan._lock_for_early_settlement()
        self.invalidate_recordset()

    def _leasing_voucher_payment_partner(self):
        self.ensure_one()
        partner = self.leasing_partner_id
        if not partner:
            raise UserError(_(
                'Leasing Partner pada Purchase Order untuk leasing %s belum diisi. '
                'Isi Leasing Partner di PO terkait sebelum membuat atau membayar voucher.',
                self.loan_id.name,
            ))
        if partner.company_id and partner.company_id != self.loan_id.company_id:
            raise UserError(_('Leasing Partner harus tersedia pada company leasing terkait.'))
        return partner

    def action_create_payment_voucher_leasing(self):
        """Action invoked from Table Leasing Detail list view to create a Payment Voucher Leasing."""
        if not self:
            raise UserError(_("Silakan pilih minimal satu baris angsuran leasing!"))

        # Khusus skema ADDM, Angsuran ke-1 sudah dibayar bersama DP (status Posted tanpa jurnal)
        eligible_lines = self.filtered(lambda l: not l._is_addm_first_installment())
        if not eligible_lines:
            raise UserError(_(
                "Angsuran ke-1 dengan skema ADDM sudah dibayar bersamaan dengan DP (berstatus Posted) "
                "dan tidak memerlukan pembentukan jurnal pembayaran."
            ))

        eligible_lines._lock_leasing_voucher_sources()

        # 1. Check if any line is already paid
        already_paid = eligible_lines.filtered(lambda l: l.vendor_bill_id)
        if already_paid:
            paid_info = ", ".join([
                f"Angs. ke-{l.installment_number} (Leasing: {l.loan_id.agreement_no or l.loan_id.name})"
                for l in already_paid
            ])
            raise UserError(_(
                "Beberapa baris angsuran yang Anda pilih sudah terbayar (memiliki Jurnal):\n%s",
                paid_info
            ))

        # 2. Check if any line is currently linked to an active voucher
        already_vouchered = eligible_lines.filtered(
            lambda l: l.leasing_voucher_id and l.leasing_voucher_id.state in ('draft', 'waiting', 'approved')
        )
        if already_vouchered:
            v_info = ", ".join([
                f"Angs. ke-{l.installment_number} (Leasing: {l.loan_id.agreement_no or l.loan_id.name}) -> {l.leasing_voucher_id.name} [{l.leasing_voucher_state}]"
                for l in already_vouchered
            ])
            raise UserError(_(
                "Beberapa baris angsuran yang Anda pilih sudah terdaftar dalam Payment Voucher yang sedang aktif:\n%s\n"
                "Harap batalkan atau selesaikan voucher tersebut terlebih dahulu.",
                v_info
            ))

        # 3. Check Company & Currency consistency
        companies = eligible_lines.mapped('loan_id.company_id')
        if len(companies) > 1:
            raise UserError(_("Semua baris angsuran yang dipilih harus berasal dari perusahaan yang sama."))
        company = companies[0] if companies else self.env.company

        currencies = eligible_lines.mapped('loan_id.currency_id')
        currency = currencies[0] if currencies else company.currency_id

        if len(currencies) > 1:
            raise UserError(_('Semua angsuran dalam voucher harus menggunakan mata uang yang sama.'))

        # Freeze the PO Leasing Partner, never the vehicle supplier/loan bank.
        config = self.env['leasing.voucher.config'].sudo().search([
            ('company_id', '=', company.id),
            ('active', '=', True),
        ], limit=1)

        partners = self.env['res.partner']
        for line in eligible_lines:
            partners |= line._leasing_voucher_payment_partner()
        same_partner_required = config.require_same_partner if config else True
        if same_partner_required and len(partners) > 1:
            raise UserError(_(
                "Konfigurasi approval mengharuskan seluruh angsuran dalam satu voucher memiliki Leasing Partner yang sama.\n"
                "Leasing Partner terpilih: %s",
                ", ".join(partners.mapped('display_name'))
            ))

        primary_partner = partners if len(partners) == 1 else False

        # 5. Create Payment Voucher in Draft
        voucher = self.env['leasing.payment.voucher'].create({
            'company_id': company.id,
            'currency_id': currency.id,
            'partner_id': primary_partner.id if primary_partner else False,
            'date': fields.Date.context_today(self),
            'state': 'draft',
            'same_partner_required': same_partner_required,
            'notes': _("Voucher pembayaran angsuran leasing untuk %s unit.") % len(eligible_lines),
        })

        # 6. Create Voucher Lines
        line_vals_list = []
        for line in eligible_lines.sorted(lambda l: (l.loan_id.id, l.installment_number)):
            loan = line.loan_id
            vehicle = line.vehicle_id or loan.vehicle_id
            line_vals_list.append({
                'voucher_id': voucher.id,
                'loan_line_id': line.id,
                'loan_id': loan.id,
                'vendor_id': line._leasing_voucher_payment_partner().id,
                'po_number': line.po_number or loan.po_number or (loan.purchase_order_id.name if hasattr(loan, 'purchase_order_id') and loan.purchase_order_id else ''),
                'vehicle_id': vehicle.id if vehicle else False,
                'license_plate': line.plate_number or (vehicle.license_plate if vehicle else (getattr(loan, 'plate_number', '') or '')),
                'installment_number': line.installment_number,
                'date': line.date,
                'principal': line.principal,
                'interest': line.interest,
                'total': line.principal + line.interest,
                'remaining_principal': getattr(line, 'outstanding_balance', 0.0),
                'remaining_interest': getattr(line, 'interest_balance', 0.0),
            })

        self.env['leasing.payment.voucher.line'].create(line_vals_list)

        # 7. Bind voucher to loan lines
        eligible_lines.write({'leasing_voucher_id': voucher.id})

        # 8. Log creation
        voucher._log('created')

        # 9. Return action to open the voucher form
        return {
            'name': _('Payment Voucher Leasing'),
            'type': 'ir.actions.act_window',
            'res_model': 'leasing.payment.voucher',
            'view_mode': 'form',
            'res_id': voucher.id,
            'target': 'current',
        }
