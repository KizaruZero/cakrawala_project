# -*- coding: utf-8 -*-
from odoo import models, fields


class AccountMove(models.Model):
    """Extend account.move to update payment_date on loan line when posted."""
    _inherit = 'account.move'

    def _post(self, soft=True):
        """Override to set payment_date on related loan line when payment move is posted."""
        posted = super()._post(soft)
        for move in posted:
            if move.generating_loan_line_id and move.is_loan_payment_move:
                loan_line = move.generating_loan_line_id
                if not loan_line.payment_date:
                    loan_line.payment_date = move.date
        return posted
