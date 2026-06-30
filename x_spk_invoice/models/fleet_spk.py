# -*- coding: utf-8 -*-
from odoo import models, fields, api

class FleetSPK(models.Model):
    _inherit = 'fleet.spk'

    invoice_ids = fields.One2many('account.move', 'fleet_spk_id', string='Invoices')
    invoice_reference = fields.Char(compute='_compute_invoice_reference', string='Invoice Reference')

    @api.depends('invoice_ids', 'invoice_ids.state', 'invoice_ids.name')
    def _compute_invoice_reference(self):
        for rec in self:
            refs = []
            for inv in rec.invoice_ids:
                if inv.state == 'draft':
                    refs.append(f"Draft ({inv.name})" if inv.name and inv.name != '/' else "Draft")
                else:
                    refs.append(inv.name or "Draft")
            rec.invoice_reference = ', '.join(refs) if refs else False

    def action_create_invoice(self):
        self.ensure_one()

        analytic_distribution = False
        if hasattr(self.vehicle_id, 'analytic_account_id') and self.vehicle_id.analytic_account_id:
            analytic_distribution = {str(self.vehicle_id.analytic_account_id.id): 100}

        invoice_vals = {
            'move_type': 'in_invoice',
            'partner_id': self.vendor_id.id if self.vendor_id else (self.customer_id.id if self.customer_id else False),
            'ref': self.name,
            'fleet_spk_id': self.id,
            'invoice_line_ids': [(0, 0, {
                'name': self.name,
                'quantity': 1,
                'price_unit': 0,
                'analytic_distribution': analytic_distribution,
            })]
        }

        invoice = self.env['account.move'].create(invoice_vals)

        return {
            'name': 'Vendor Bill',
            'type': 'ir.actions.act_window',
            'view_mode': 'form',
            'res_model': 'account.move',
            'res_id': invoice.id,
            'target': 'current',
        }
