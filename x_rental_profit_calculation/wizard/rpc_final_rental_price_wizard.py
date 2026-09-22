# -*- coding: utf-8 -*-
from odoo import fields, models, _
from odoo.exceptions import UserError


class RpcFinalRentalPriceWizard(models.TransientModel):
    _name = 'rpc.final.rental.price.wizard'
    _description = 'RPC Final Rental Price Approval'

    document_id = fields.Many2one(
        'rpc.document',
        string='Dokumen RPC',
        required=True,
        readonly=True,
    )
    currency_id = fields.Many2one(
        related='document_id.currency_id',
        readonly=True,
    )
    upper_price = fields.Monetary(
        related='document_id.sewa_per_bulan_batas_atas',
        string='Harga Sewa/Bulan Batas Atas',
        currency_field='currency_id',
        readonly=True,
    )
    lower_price = fields.Monetary(
        related='document_id.sewa_per_bulan_batas_bawah',
        string='Harga Sewa/Bulan Batas Bawah',
        currency_field='currency_id',
        readonly=True,
    )
    price_choice = fields.Selection(
        [
            ('upper', 'Batas Atas'),
            ('lower', 'Batas Bawah'),
        ],
        string='Harga Final',
    )
    rejection_reason = fields.Text(string='Alasan Reject')

    def _validate_final_approver(self):
        self.ensure_one()
        document = self.document_id.exists()
        if not document or document.state != 'waiting_approval':
            raise UserError(_(
                'Dokumen RPC tidak lagi berada pada status Waiting Approval.'
            ))
        stage = document.next_approval_stage_id.exists()
        if not stage or not stage._can_user_approve(self.env.user):
            raise UserError(_(
                'Anda bukan approver pada tahap approval terakhir ini.'
            ))
        next_stage = self.env['rpc.approval.stage'].search([
            ('active', '=', True),
            ('sequence', '>', stage.sequence),
        ], order='sequence, id', limit=1)
        if next_stage:
            raise UserError(_(
                'Pemilihan Harga Sewa/Bulan final hanya dilakukan pada '
                'approval sequence terakhir.'
            ))
        return document

    def action_approve_final_price(self):
        document = self._validate_final_approver()
        if self.price_choice not in ('upper', 'lower'):
            raise UserError(_(
                'Pilih Harga Sewa/Bulan Batas Atas atau Batas Bawah.'
            ))
        final_price = (
            document.sewa_per_bulan_batas_atas
            if self.price_choice == 'upper'
            else document.sewa_per_bulan_batas_bawah
        )
        if final_price <= 0:
            raise UserError(_('Harga Sewa/Bulan final harus lebih besar dari 0.'))
        document.write({
            'final_rental_price_type': self.price_choice,
            'final_rental_price': final_price,
        })
        document.message_post(body=_(
            '%s memilih Harga Sewa/Bulan %s sebagai harga final: %s %s.'
        ) % (
            self.env.user.display_name,
            dict(self._fields['price_choice']._description_selection(
                self.env
            )).get(self.price_choice),
            document.currency_id.symbol or '',
            format(final_price, ',.2f'),
        ))
        return document.with_context(
            rpc_skip_final_price_wizard=True
        ).action_approve()

    def action_reject(self):
        document = self._validate_final_approver()
        reason = (self.rejection_reason or '').strip()
        if not reason:
            raise UserError(_('Alasan Reject wajib diisi.'))
        document._revise_to_draft(
            _('Ditolak pada approval harga final: %s') % reason,
            revised_by=self.env.user,
        )
        return {'type': 'ir.actions.act_window_close'}
