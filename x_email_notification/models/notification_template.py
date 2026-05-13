from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError



class NotificationTemplate(models.Model):
    _name = 'x.notification.template'
    _description = 'Notification Template'
    _rec_name = 'name'

    name = fields.Char(
        string='Notification Name',
        required=True
    )

    code = fields.Char(
        string='Code',
        required=True,
        copy=False
    )

    active = fields.Boolean(
        default=True
    )

    model_id = fields.Many2one(
        'ir.model',
        string='Related Model',
        required=True,
        ondelete='cascade',
    )

    mail_template_id = fields.Many2one(
        'mail.template',
        string='Mail Template',
        required=True,
        domain="[('model_id', '=', model_id)]"
    )

    notes = fields.Text()

    _sql_constraints = [
        (
            'unique_notification_code',
            'unique(code)',
            'Notification code must be unique.'
        )
    ]

    def send_notification(self, code, record, template_context=None, email_values=None):
        """
        Generic send notification method.

        Optional *template_context* is merged into the environment used to
        render ``mail.template`` (available in placeholders as ``ctx``, e.g.
        ``{{ ctx.get('bastk_reminder_label') }}``).

        Optional *email_values* is passed to ``mail.template.send_mail`` and
        can override ``email_to`` / ``recipient_ids`` when the template has
        no recipient (e.g. fleet document → insurer).

        Example:
            self.env['x.notification.template'].send_notification(
                code='spk_approved',
                record=self,
            )
        """

        template = self.search([
            ('code', '=', code),
            ('active', '=', True)
        ], limit=1)

        if not template:
            raise UserError(
                f'Notification template with code "{code}" not found.'
            )

        if not template.mail_template_id:
            raise UserError(
                'Mail template is empty.'
            )

        mail_template = template.mail_template_id
        if template_context:
            mail_template = mail_template.with_context(**template_context)

        mail_template.send_mail(
            record.id,
            force_send=True,
            email_values=email_values,
        )

        return True

    def action_open_mail_template(self):

        self.ensure_one()

        return {
            'type': 'ir.actions.act_window',
            'name': 'Mail Template',
            'res_model': 'mail.template',
            'view_mode': 'form',
            'res_id': self.mail_template_id.id,
            'target': 'current',
        }
        
    @api.constrains('model_id', 'mail_template_id')
    def _check_model_consistency(self):

        for rec in self:

            if rec.mail_template_id.model_id != rec.model_id:
                raise ValidationError(
                    'Related Model and Mail Template model must match.'
                )