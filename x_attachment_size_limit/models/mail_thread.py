from odoo import api, models

from .ir_attachment import SKIP_CONTEXT_KEY


class MailThread(models.AbstractModel):
    _inherit = 'mail.thread'

    @api.model
    def message_process(self, model, message, custom_values=None,
                        save_original=False, strip_attachments=False,
                        thread_id=None):
        # Incoming emails may arrive through the mailgate RPC (an HTTP request):
        # rejecting one attachment would drop the whole email.
        return super(MailThread, self.with_context(**{SKIP_CONTEXT_KEY: True})).message_process(
            model, message, custom_values=custom_values,
            save_original=save_original, strip_attachments=strip_attachments,
            thread_id=thread_id,
        )
