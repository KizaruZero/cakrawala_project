# -*- coding: utf-8 -*-
from markupsafe import Markup, escape

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

        source_state = document.state
        state_labels = dict(
            document._fields['state']._description_selection(self.env)
        )
        source_label = state_labels.get(source_state, source_state)
        target_label = state_labels.get('draft', 'Draft')

        document.with_context(tracking_disable=True).write({
            'state': 'draft',
        })
        document.insurance_line_ids.unlink()
        (
            document.finance_unit_line_ids
            | document.finance_cashflow_line_ids
        ).unlink()
        document.logic_table_ids.unlink()
        document._clear_funding_and_gapping_lines()
        document.rpc_profitability_line_ids.unlink()

        document.message_post(body=Markup(
            '<b>%s</b><br/>'
            '%s: <b>%s</b> → <b>%s</b><br/>'
            '%s: %s<br/>'
            '%s:<div style="white-space: pre-wrap;">%s</div>'
        ) % (
            escape(_('RPC Direvisi')),
            escape(_('Perubahan Stage')),
            escape(source_label),
            escape(target_label),
            escape(_('Direvisi Oleh')),
            escape(self.env.user.display_name),
            escape(_('Revise Reason')),
            escape(reason),
        ))
        return {'type': 'ir.actions.act_window_close'}
