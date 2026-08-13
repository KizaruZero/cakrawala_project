import logging
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools.misc import format_date, formatLang

from .notification_template import INVOICE_DUE_NOTIFICATION_SCOPE

_logger = logging.getLogger(__name__)

_DEFAULT_INVOICE_DUE_REMINDERS = (
    ('D14', 'H-14 hari', lambda due, today: due - timedelta(days=14) == today),
    ('D7', 'H-7 hari', lambda due, today: due - timedelta(days=7) == today),
    ('D3', 'H-3 hari', lambda due, today: due - timedelta(days=3) == today),
)

INVOICE_DUE_SETTLED_PAYMENT_STATES = ('paid', 'reversed', 'blocked', 'invoicing_legacy')


class AccountMove(models.Model):
    _inherit = 'account.move'

    invoice_due_reminder_stages_sent = fields.Char(
        string='Due-date reminder stages sent',
        copy=False,
        help='Comma-separated reminder stage keys already sent (see Notification template '
             '«End-date reminders»). Defaults to D14, D7, D3. Reset when Due Date changes.',
    )
    invoice_due_send_label = fields.Char(
        string='Due-date reminder label (email render)',
        copy=False,
        help='Set only while sending the due-date email; use object.invoice_due_send_label '
             'in the mail body.',
    )
    invoice_email_display_date = fields.Char(
        compute='_compute_invoice_email_display_fields',
        string='Invoice date (email)',
    )
    invoice_email_display_due = fields.Char(
        compute='_compute_invoice_email_display_fields',
        string='Due date (email)',
    )
    invoice_email_display_total = fields.Char(
        compute='_compute_invoice_email_display_fields',
        string='Total (email)',
    )
    invoice_email_display_residual = fields.Char(
        compute='_compute_invoice_email_display_fields',
        string='Amount due (email)',
    )

    @api.depends('invoice_date', 'invoice_date_due', 'amount_total', 'amount_residual', 'currency_id')
    def _compute_invoice_email_display_fields(self):
        for move in self:
            move.invoice_email_display_date = (
                format_date(move.env, move.invoice_date) if move.invoice_date else ''
            )
            move.invoice_email_display_due = (
                format_date(move.env, move.invoice_date_due) if move.invoice_date_due else ''
            )
            move.invoice_email_display_total = formatLang(
                move.env, move.amount_total, currency_obj=move.currency_id
            )
            move.invoice_email_display_residual = formatLang(
                move.env, move.amount_residual, currency_obj=move.currency_id
            )

    def write(self, vals):
        if vals and 'invoice_date_due' in vals:
            vals = dict(vals)
            vals['invoice_due_reminder_stages_sent'] = False
            vals['invoice_due_send_label'] = False
        return super().write(vals)

    @api.model
    def _invoice_due_active_reminder_schedule(self):
        """Reminder lines on the active «Use for = Invoice» template, else the default."""
        Notif = self.env['x.notification.template'].sudo()
        template = Notif.get_template_for_scope_model(
            INVOICE_DUE_NOTIFICATION_SCOPE,
            'account.move',
        )
        if template and template.reminder_line_ids:
            return template.iter_end_date_reminder_checks()
        return list(_DEFAULT_INVOICE_DUE_REMINDERS)

    def _get_invoice_due_stages_sent(self):
        self.ensure_one()
        if not self.invoice_due_reminder_stages_sent:
            return set()
        return {
            x.strip()
            for x in self.invoice_due_reminder_stages_sent.split(',')
            if x.strip()
        }

    def _invoice_due_notification_email_values(self):
        """Build recipients: invoice partner, its commercial parent, then the salesperson."""
        self.ensure_one()
        candidates = []
        for partner in (
            self.partner_id,
            self.commercial_partner_id,
            self.invoice_user_id.partner_id,
        ):
            if partner and partner not in candidates:
                candidates.append(partner)

        for partner in candidates:
            if partner.email:
                return {
                    'email_to': partner.email_formatted,
                    'recipient_ids': [(6, 0, [partner.id])],
                }

        _logger.warning(
            'Invoice %s (%s): customer / salesperson partner has no email; '
            'cannot send INVOICE due-date notification.',
            self.id,
            self.display_name or '',
        )
        return None

    def _invoice_send_due_notify(self, stage_key, stage_label):
        self.ensure_one()
        template_context = {
            'invoice_reminder_stage': stage_key,
            'invoice_reminder_label': stage_label,
        }
        email_values = self._invoice_due_notification_email_values()
        if not email_values:
            return False

        bookkeeping = self.with_context(skip_is_manually_modified=True)
        bookkeeping.write({'invoice_due_send_label': stage_label})
        try:
            self.env['x.notification.template'].sudo().send_notification_for_scope(
                self,
                INVOICE_DUE_NOTIFICATION_SCOPE,
                template_context=template_context,
                email_values=email_values,
            )
            return True
        except UserError as err:
            _logger.warning(
                'Invoice due-date reminder skipped (record %s, stage %s): %s',
                self.id, stage_key, err,
            )
            return False
        finally:
            bookkeeping.write({'invoice_due_send_label': False})

    @api.model
    def cron_send_invoice_due_notifications(self):
        """Daily: customer invoice due-date emails via «Use for = Invoice» template.

        Schedule comes from the template's «End-date reminders» lines when configured,
        otherwise H-14 / H-7 / H-3 calendar days before invoice_date_due.

        Mail subject may use {{ }}; body QWeb must use simple t-out paths only
        (e.g. object.invoice_due_send_label, object.invoice_email_display_due).
        """
        reminders = self._invoice_due_active_reminder_schedule()
        today = fields.Date.today()
        candidates = self.search([
            ('move_type', '=', 'out_invoice'),
            ('state', '=', 'posted'),
            ('invoice_date_due', '!=', False),
            ('payment_state', 'not in', INVOICE_DUE_SETTLED_PAYMENT_STATES),
            ('amount_residual', '>', 0),
        ])
        for rec in candidates:
            due = rec.invoice_date_due
            if due < today:
                continue
            sent = rec._get_invoice_due_stages_sent()
            new_stages = []
            for stage_key, stage_label, predicate in reminders:
                if stage_key in sent:
                    continue
                if not predicate(due, today):
                    continue
                if rec._invoice_send_due_notify(stage_key, stage_label):
                    new_stages.append(stage_key)
            if new_stages:
                rec.with_context(skip_is_manually_modified=True).write({
                    'invoice_due_reminder_stages_sent': ','.join(sorted(sent | set(new_stages))),
                })
