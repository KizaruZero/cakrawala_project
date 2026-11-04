# -*- coding: utf-8 -*-
from odoo import fields, models

STOP_DEFERRED_WARNING_MESSAGE = (
    "Untuk unit yang dilakukan early termination jangan lupa untuk melakukan "
    "step stop deferred pada STNK dan Asuransi terkait unit tersebut"
)


class ETCreateInvoiceWarningWizard(models.TransientModel):
    _name = 'et.create.invoice.warning.wizard'
    _description = 'Early Termination Create Invoice Warning Wizard'

    et_line_id = fields.Many2one(
        'sale.order.et.line',
        string='Early Termination Line',
        required=True,
        readonly=True,
        ondelete='cascade',
    )
    order_id = fields.Many2one(related='et_line_id.order_id', readonly=True)
    unit_summary = fields.Char(related='et_line_id.unit_summary', string='Units', readonly=True)
    currency_id = fields.Many2one(related='et_line_id.currency_id', readonly=True)
    penalty_amount = fields.Monetary(
        related='et_line_id.penalty_amount',
        currency_field='currency_id',
        string='Penalty Amount',
        readonly=True,
    )
    warning_message = fields.Text(
        string='Warning Message',
        default=STOP_DEFERRED_WARNING_MESSAGE,
        readonly=True,
    )

    def action_confirm_create_invoice(self):
        self.ensure_one()
        return self.et_line_id._create_penalty_invoice()

