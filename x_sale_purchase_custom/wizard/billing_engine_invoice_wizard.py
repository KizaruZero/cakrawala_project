# -*- coding: utf-8 -*-
from odoo import _, models


class RentalBillingEngineInvoiceWizard(models.TransientModel):
    _name = 'rental.billing.engine.invoice.wizard'
    _description = 'Generate Invoices from Rental Billing Engine'

    def action_generate(self):
        self.ensure_one()
        invoices = self.env['sale.order']._generate_billing_engine_invoices()
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
