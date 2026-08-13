from odoo import api, fields, models

INVOICE_DUE_NOTIFICATION_SCOPE = 'invoice_due'


class NotificationTemplate(models.Model):
    _inherit = 'x.notification.template'

    notification_scope = fields.Selection(
        selection_add=[
            (
                INVOICE_DUE_NOTIFICATION_SCOPE,
                'Invoice — customer invoice due-date reminders',
            ),
        ],
        ondelete={INVOICE_DUE_NOTIFICATION_SCOPE: 'cascade'},
    )

    @api.model
    def _scopes_with_unique_binding(self):
        return super()._scopes_with_unique_binding() | {INVOICE_DUE_NOTIFICATION_SCOPE}
