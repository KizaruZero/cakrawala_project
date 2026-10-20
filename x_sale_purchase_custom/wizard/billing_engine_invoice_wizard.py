# -*- coding: utf-8 -*-
from odoo import Command, _, api, fields, models


class RentalBillingEngineInvoiceWizard(models.TransientModel):
    _name = 'rental.billing.engine.invoice.wizard'
    _description = 'Generate Invoices from Rental Billing Engine'

    generated_invoice_ids = fields.Many2many('account.move', readonly=True)
    generated_invoice_count = fields.Integer(compute='_compute_generated_invoice_count')
    skipped_order_count = fields.Integer(readonly=True)
    skipped_orders_report = fields.Text(readonly=True)

    @api.depends('generated_invoice_ids')
    def _compute_generated_invoice_count(self):
        for wizard in self:
            wizard.generated_invoice_count = len(wizard.generated_invoice_ids)

    def action_generate(self):
        self.ensure_one()
        skipped = []
        invoices = self.env['sale.order']._generate_billing_engine_invoices(
            due_only=False, current_month_only=False, skip_report=skipped,
        )
        if skipped:
            self.write({
                'generated_invoice_ids': [Command.set(invoices.ids)],
                'skipped_order_count': len(skipped),
                'skipped_orders_report': '\n\n'.join(
                    '%s: %s' % (item['order_name'], item['reason']) for item in skipped
                ),
            })
            return {
                'type': 'ir.actions.act_window',
                'name': _('Invoice Generation Results'),
                'res_model': self._name,
                'res_id': self.id,
                'view_mode': 'form',
                'views': [(self.env.ref(
                    'x_sale_purchase_custom.view_billing_engine_invoice_wizard_result_form',
                ).id, 'form')],
                'target': 'new',
            }
        if not invoices:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Generate Invoices'),
                    'message': _('No eligible uninvoiced Billing Engine rows were found.'),
                    'type': 'info',
                    'sticky': False,
                    'next': {'type': 'ir.actions.act_window_close'},
                },
            }

        return self._generated_invoice_action(invoices)

    def action_view_generated_invoices(self):
        self.ensure_one()
        if not self.generated_invoice_ids:
            return {'type': 'ir.actions.act_window_close'}
        return self._generated_invoice_action(self.generated_invoice_ids)

    def _generated_invoice_action(self, invoices):
        action = self.env['ir.actions.actions']._for_xml_id(
            'account.action_move_out_invoice_type'
        )
        action.update({
            'name': _('Generated Rental Invoices'),
            'domain': [('id', 'in', invoices.ids)],
            'context': {
                'default_move_type': 'out_invoice',
                'default_x_is_rental_invoice': True,
                'group_by': ['invoice_origin', 'partner_id'],
            },
        })
        return action
