import base64

from odoo import _, fields, models
from odoo.exceptions import UserError

from .soa_pdf import build_statement_pdf


class AccountMove(models.Model):
    _inherit = 'account.move'

    def action_create_statement_of_account(self):
        moves = self.filtered(lambda move: move.move_type == 'out_invoice')
        if not moves:
            raise UserError(_('Please select at least one customer invoice.'))

        partners = moves.mapped('commercial_partner_id')
        if len(partners) != 1:
            raise UserError(_(
                'Statement of Account can only be generated with the same customer'
            ))

        partner = partners[0]
        pdf_content = build_statement_pdf(
            moves.sorted(lambda move: (move.invoice_date or move.date, move.name)),
            self.env.company,
            partner,
        )
        filename = 'Statement of Account - %s.pdf' % partner.display_name
        attachment = self.env['ir.attachment'].create({
            'name': filename,
            'type': 'binary',
            'datas': base64.b64encode(pdf_content),
            'mimetype': 'application/pdf',
            'res_model': 'account.move',
            'res_id': moves[0].id,
        })

        company = self.env.company
        body = _(
            '<p>Dear %(partner)s,</p>'
            '<p>Please find enclosed the statement of your account.</p>'
            '<p>Do not hesitate to contact us if you have any questions.</p>'
            '<p>Sincerely,<br/>%(company)s</p>',
            partner=partner.name,
            company=company.name,
        )
        wizard = self.env['customer.statement.soa.email.wizard'].create({
            'partner_id': partner.id,
            'email_to': partner.email or '',
            'subject': _('%(company)s Statement - %(partner)s',
                         company=company.name, partner=partner.name),
            'body': body,
            'attachment_ids': [(6, 0, attachment.ids)],
            'move_ids': [(6, 0, moves.ids)],
        })
        return {
            'type': 'ir.actions.act_window',
            'name': _('Send %s Statement', partner.display_name),
            'res_model': 'customer.statement.soa.email.wizard',
            'view_mode': 'form',
            'view_id': self.env.ref('customer_statement_soa.view_soa_email_wizard_form').id,
            'res_id': wizard.id,
            'target': 'new',
        }

    def _soa_aging_label(self):
        self.ensure_one()
        if not self.invoice_date_due:
            return ''
        days = (fields.Date.context_today(self) - self.invoice_date_due).days
        if days > 0:
            return _('%s Days', days)
        if days == 0:
            return _('Due Today')
        return _('In %s Days', abs(days))
