# Part of x_email_notification.
# Child rows of x.notification.template: Odoo requires template_id (the inverse
# of reminder_line_ids) to store the foreign key in the database — it is not
# “redundant”, just the back-reference from line → parent.
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class NotificationReminderLine(models.Model):
    _name = 'x.notification.reminder.line'
    _description = 'Reminder schedule (days before end date)'
    _order = 'days_before_end desc, id'

    template_id = fields.Many2one(
        'x.notification.template',
        required=True,
        ondelete='cascade',
        index=True,
    )
    days_before_end = fields.Integer(
        string='Days before end date',
        required=True,
        help='Email is sent on the day when (end date − this many days) equals today.',
    )

    _sql_constraints = [
        (
            'reminder_days_unique',
            'unique(template_id, days_before_end)',
            'Each “days before end” value must appear only once per notification template.',
        ),
    ]

    def _reminder_stage_key(self):
        self.ensure_one()
        return 'D%d' % self.days_before_end

    def _reminder_stage_label(self):
        self.ensure_one()
        return _('H-%s hari') % self.days_before_end

    def reminder_predicate(self):
        """(end_date, today_date) -> bool"""
        self.ensure_one()
        d = self.days_before_end
        return lambda end, today, d=d: end - timedelta(days=d) == today

    @api.constrains('days_before_end')
    def _check_days_positive(self):
        for line in self:
            if line.days_before_end < 1:
                raise ValidationError(_('Use at least 1 day before the end date.'))
