from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class NotificationTemplate(models.Model):
    _name = 'x.notification.template'
    _description = 'Notification Template'
    _rec_name = 'name'

    name = fields.Char(
        string='Notification Name',
        required=True
    )

    notification_scope = fields.Selection(
        [
            ('general', 'General — other / manual'),
            ('bastk', 'BASTK — end-date reminder emails'),
            (
                'fleet_contract',
                'Fleet — vehicle contract / insurance expiry reminders',
            ),
            (
                'service_planning_km',
                'Service Planning — odometer & interval reminder emails',
            ),
        ],
        string='Use for',
        required=True,
        default='general',
        index=True,
        help='Which application cron or flow uses this row. Pick one place only per document model '
             '(e.g. one “BASTK” template for model BASTK Management). '
             'Avoids typing technical codes in Python.',
    )

    code = fields.Char(
        string='Technical code (optional)',
        copy=False,
        help='Optional. Legacy identifier for code-based API: send_notification(code, record). '
             'Prefer “Use for” + Related model instead.',
    )

    reminder_line_ids = fields.One2many(
        'x.notification.reminder.line',
        'template_id',
        string='End-date reminders',
        copy=True,
        help='Reminders N days before an end date. Used when “Use for” is BASTK (or similar flows). '
             'Leave empty to use the built-in default on the BASTK cron.',
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

    @api.constrains('code')
    def _check_code_unique_when_set(self):
        for rec in self:
            if not rec.code:
                continue
            if self.search_count([
                ('code', '=', rec.code),
                ('id', '!=', rec.id),
            ]):
                raise ValidationError(
                    _('Technical code "%s" is already used on another template.') % rec.code
                )

    @api.model
    def _scopes_with_unique_binding(self):
        """Scopes where a single active template per model is the whole point.

        Modules that add a scope through ``selection_add`` extend this set so the
        “only one active row” rule follows their scope too.
        """
        return {'bastk', 'fleet_contract'}

    @api.constrains('notification_scope', 'model_id', 'active')
    def _check_one_active_per_scope_and_model(self):
        """One active binding per (Use for, model) for app-specific scopes."""
        scoped = self._scopes_with_unique_binding()
        for rec in self:
            if rec.notification_scope not in scoped or not rec.active:
                continue
            if self.search_count([
                ('notification_scope', '=', rec.notification_scope),
                ('model_id', '=', rec.model_id.id),
                ('active', '=', True),
                ('id', '!=', rec.id),
            ]):
                raise ValidationError(
                    _('Only one active “%(scope)s” template is allowed for model %(model)s.')
                    % {
                        'scope': dict(rec._fields['notification_scope'].selection).get(
                            rec.notification_scope, rec.notification_scope
                        ),
                        'model': rec.model_id.display_name or rec.model_id.model,
                    }
                )

    def _send_mail_from_template(
        self, template, record, template_context=None, email_values=None
    ):
        if not template.mail_template_id:
            raise UserError(_('Mail template is empty.'))
        mail_template = template.mail_template_id
        if template_context:
            mail_template = mail_template.with_context(**template_context)
        mail_template.send_mail(
            record.id,
            force_send=True,
            email_values=email_values,
        )
        return True

    @api.model
    def send_notification_for_scope(
        self, record, scope, template_context=None, email_values=None
    ):
        """Resolve template by *Use for* + record model (no code)."""
        if scope == 'general':
            raise UserError(_('Choose a specific app under “Use for”, not General.'))
        model_id = self.env['ir.model']._get_id(record._name)
        template = self.search(
            [
                ('notification_scope', '=', scope),
                ('model_id', '=', model_id),
                ('active', '=', True),
            ],
            limit=1,
            order='id asc',
        )
        if not template:
            raise UserError(
                _(
                    'No active notification template with “Use for” = %(scope)s for model %(model)s. '
                    'Create one under Fleet → Configuration → Notifications.'
                )
                % {
                    'scope': dict(self._fields['notification_scope'].selection).get(scope, scope),
                    'model': record._name,
                }
            )
        return self._send_mail_from_template(
            template, record, template_context=template_context, email_values=email_values
        )

    def send_notification(self, code, record, template_context=None, email_values=None):
        """
        Legacy: find row by *code* (must be filled on that template).

        Prefer :meth:`send_notification_for_scope` and “Use for” on the master row.
        """

        template = self.search(
            [('code', '=', code), ('active', '=', True)], limit=1
        )

        if not template:
            raise UserError(
                _('No notification template with technical code “%s”.') % code
            )

        return self._send_mail_from_template(
            template, record, template_context=template_context, email_values=email_values
        )

    @api.model
    def get_template_for_scope_model(self, scope, model_name):
        """Return the active notification.template for this app binding, or empty recordset."""
        model_id = self.env['ir.model']._get_id(model_name)
        return self.search(
            [
                ('notification_scope', '=', scope),
                ('model_id', '=', model_id),
                ('active', '=', True),
            ],
            limit=1,
            order='id asc',
        )

    def iter_end_date_reminder_checks(self):
        """Return [(stage_code, stage_label, predicate), ...] with predicate(end_date, today_date)->bool.

        Empty list if no reminder lines; callers may fall back to their own defaults.
        """
        self.ensure_one()
        result = []
        for line in self.reminder_line_ids:
            result.append((
                line._reminder_stage_key(),
                line._reminder_stage_label(),
                line.reminder_predicate(),
            ))
        return result

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