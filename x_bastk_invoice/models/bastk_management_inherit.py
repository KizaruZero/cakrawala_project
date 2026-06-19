from odoo import models, fields, api

class BastkManagement(models.Model):
    _inherit = 'bastk.management'

    invoice_ids = fields.One2many('account.move', 'bastk_id', string='Invoices')
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
            'move_type': 'out_invoice',
            'partner_id': self.partner_id.id,
            'ref': self.name,
            'bastk_id': self.id,
            'invoice_line_ids': [(0, 0, {
                'name': self.name,
                'analytic_distribution': analytic_distribution,
            })]
        }
        
        invoice = self.env['account.move'].create(invoice_vals)
        
        return {
            'name': 'Customer Invoice',
            'type': 'ir.actions.act_window',
            'view_mode': 'form',
            'res_model': 'account.move',
            'res_id': invoice.id,
            'target': 'current',
        }
