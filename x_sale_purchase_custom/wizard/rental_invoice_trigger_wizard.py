# -*- coding: utf-8 -*-
from odoo import models, fields, api, _

class RentalInvoiceTriggerWizard(models.TransientModel):
    _name = 'x.rental.invoice.trigger.wizard'
    _description = 'Trigger Draft Rental Invoices Wizard'

    trigger_date = fields.Date(
        string='Trigger Date',
        default=fields.Date.context_today,
        required=False,
        help="Local date used to evaluate and generate due rental invoice cycles across all confirmed rental orders."
    )

    def action_trigger_invoices(self):
        self.ensure_one()
        target_date = self.trigger_date or fields.Date.context_today(self)
        # Find all active rental sales orders
        rental_orders = self.env['sale.order'].search([
            ('is_rental_order', '=', True),
            ('state', 'in', ('sale', 'done')),
        ])
        
        before_draft_ids = set(self.env['account.move'].search([
            ('x_is_rental_invoice', '=', True),
            ('state', '=', 'draft'),
        ]).ids)

        for order in rental_orders:
            try:
                order._generate_rental_invoices_if_due(today=target_date)
            except Exception:
                continue

        after_draft_invoices = self.env['account.move'].search([
            ('x_is_rental_invoice', '=', True),
            ('state', '=', 'draft'),
        ])
        after_draft_ids = set(after_draft_invoices.ids)
        new_ids = after_draft_ids - before_draft_ids

        action = self.env['ir.actions.actions']._for_xml_id('account.action_move_out_invoice_type')
        if new_ids:
            action['domain'] = [('id', 'in', list(new_ids))]
        else:
            action['domain'] = [('id', 'in', list(after_draft_ids))]
        
        action['context'] = {
            'default_move_type': 'out_invoice',
            'default_x_is_rental_invoice': True,
            'search_default_group_by_invoice_origin': 1,
            'search_default_group_by_partner_id': 1,
            'group_by': ['invoice_origin', 'partner_id'],
        }
        action['name'] = _('Triggered Draft Rental Invoices')
        return action
