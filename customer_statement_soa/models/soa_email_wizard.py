from odoo import _, fields, models
from odoo.exceptions import UserError


class SoaEmailWizard(models.TransientModel):
    _name = 'customer.statement.soa.email.wizard'
    _description = 'Send Statement of Account Email'

    partner_id = fields.Many2one('res.partner', required=True, readonly=True)
    email_to = fields.Char(string='Recipients', required=True)
    subject = fields.Char(required=True)
    body = fields.Html(required=True)
    attachment_ids = fields.Many2many('ir.attachment', string='Attachments', readonly=True)
    move_ids = fields.Many2many('account.move', readonly=True)

    def action_send(self):
        self.ensure_one()
        if not self.email_to:
            raise UserError(_('The customer must have an email address before sending a statement.'))

        mail = self.env['mail.mail'].create({
            'subject': self.subject,
            'body_html': self.body,
            'email_to': self.email_to,
            'attachment_ids': [(6, 0, self.attachment_ids.ids)],
            'model': 'account.move',
            'res_id': self.move_ids[:1].id,
            'auto_delete': False,
        })
        try:
            mail.send(raise_exception=True)
        except Exception as error:
            raise UserError(_('The email could not be sent: %s', error)) from error

        for move in self.move_ids:
            move.message_post(
                body=_('Statement of Account sent to %s.', self.email_to),
                attachment_ids=self.attachment_ids.ids,
            )
        return {'type': 'ir.actions.act_window_close'}
