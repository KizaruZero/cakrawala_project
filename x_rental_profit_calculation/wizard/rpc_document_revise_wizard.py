# -*- coding: utf-8 -*-
from odoo import fields, models, _
from odoo.exceptions import UserError


class RpcDocumentReviseWizard(models.TransientModel):
    _name = 'rpc.document.revise.wizard'
    _description = 'RPC Revise Reason Wizard'

    document_id = fields.Many2one(
        'rpc.document',
        string='Dokumen RPC',
        required=True,
        readonly=True,
    )
    source_state = fields.Selection(
        related='document_id.state',
        string='Stage Saat Ini',
        readonly=True,
    )
    revise_reason = fields.Text(string='Revise Reason', required=True)

    def action_confirm_revise(self):
        self.ensure_one()
        document = self.document_id.exists()
        if not document:
            raise UserError(_('Dokumen RPC tidak ditemukan.'))
        if document.state in ('draft', 'cancelled'):
            raise UserError(_(
                'Dokumen pada stage Draft atau Cancelled tidak dapat direvisi.'
            ))

        reason = (self.revise_reason or '').strip()
        if not reason:
            raise UserError(_('Revise Reason wajib diisi.'))

        document._revise_to_draft(reason, revised_by=self.env.user)
        return {'type': 'ir.actions.act_window_close'}
