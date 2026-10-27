# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


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

    def action_create_payment_voucher_leasing(self):
        """Action invoked from Table Leasing Detail list view to create a Payment Voucher Leasing."""
        if not self:
            raise UserError(_("Silakan pilih minimal satu baris angsuran leasing!"))

        # 1. Check if any line is already paid
        already_paid = self.filtered(lambda l: l.vendor_bill_id)
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
        already_vouchered = self.filtered(
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
        companies = self.mapped('loan_id.company_id')
        if len(companies) > 1:
            raise UserError(_("Semua baris angsuran yang dipilih harus berasal dari perusahaan yang sama."))
        company = companies[0] if companies else self.env.company

        currencies = self.mapped('loan_id.currency_id')
        currency = currencies[0] if currencies else company.currency_id

        # 4. Check Vendor consistency if required by config
        config = self.env['leasing.voucher.config'].sudo().search([
            ('company_id', '=', company.id),
            ('active', '=', True),
        ], limit=1)

        vendors = self.mapped('loan_id.vendor_id')
        if config and config.require_same_partner and len(vendors) > 1:
            raise UserError(_(
                "Konfigurasi approval mengharuskan seluruh baris angsuran dalam satu voucher berasal dari Vendor/Leasing Partner yang sama.\n"
                "Vendor terpilih: %s",
                ", ".join(vendors.mapped('display_name'))
            ))

        primary_vendor = vendors[0] if len(vendors) == 1 else False

        # 5. Create Payment Voucher in Draft
        voucher = self.env['leasing.payment.voucher'].create({
            'company_id': company.id,
            'currency_id': currency.id,
            'partner_id': primary_vendor.id if primary_vendor else False,
            'date': fields.Date.context_today(self),
            'state': 'draft',
            'same_partner_required': config.require_same_partner if config else True,
            'notes': _("Voucher pembayaran angsuran leasing untuk %s unit.") % len(self),
        })

        # 6. Create Voucher Lines
        line_vals_list = []
        for line in self.sorted(lambda l: (l.loan_id.id, l.installment_number)):
            loan = line.loan_id
            vehicle = line.vehicle_id or loan.vehicle_id
            line_vals_list.append({
                'voucher_id': voucher.id,
                'loan_line_id': line.id,
                'loan_id': loan.id,
                'vendor_id': loan.vendor_id.id if loan.vendor_id else False,
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
        self.write({'leasing_voucher_id': voucher.id})

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
