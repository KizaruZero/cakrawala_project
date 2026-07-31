import base64

from odoo import _, fields, models
from odoo.exceptions import UserError

from .soa_pdf import build_statement_pdf


class AccountMove(models.Model):
    _inherit = 'account.move'

    def action_create_statement_of_account(self):
        if not self:
            raise UserError(_('Please select at least one customer invoice.'))

        moves = self.filtered(
            lambda move: (
                move.move_type == 'out_invoice'
                and move.state == 'posted'
                and move.amount_residual > 0
            )
        )
        if not moves:
            if self.filtered(lambda move: move.move_type == 'out_invoice' and move.state == 'posted'):
                raise UserError(_(
                    'Please select at least one posted customer invoice with an outstanding balance.'
                ))
            if self.filtered(lambda move: move.move_type == 'out_invoice'):
                raise UserError(_(
                    'Statement of Account can only be generated from posted customer invoices.'
                ))
            raise UserError(_('Please select at least one customer invoice.'))

        partners = moves.mapped('commercial_partner_id')
        if len(partners) != 1:
            raise UserError(_(
                'Statement of Account can only be generated for invoices belonging to the same customer. '
                'Selected customers: %(customers)s',
                customers=', '.join(partners.mapped('display_name')),
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

    def _soa_is_overdue(self):
        self.ensure_one()
        if not self.invoice_date_due:
            return False
        return (fields.Date.context_today(self) - self.invoice_date_due).days > 0

    def _soa_aging_label(self):
        self.ensure_one()
        if not self.invoice_date_due:
            return ''
        days = (fields.Date.context_today(self) - self.invoice_date_due).days
        if days > 0:
            return _('%s Days Ago', days)
        if days == 0:
            return _('Due Today')
        return _('In %s Days', abs(days))
