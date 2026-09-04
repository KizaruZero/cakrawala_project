# -*- coding: utf-8 -*-
from odoo import api, fields, models, _


class PurchaseOrder(models.Model):
    """Extend purchase.order with smart button to Leasing Schedule."""
    _inherit = 'purchase.order'

    leasing_loan_ids = fields.One2many(
        'account.loan',
        'purchase_order_id',
        string='Leasing Schedules',
    )
    leasing_loan_count = fields.Integer(
        string='Leasing Count',
        compute='_compute_leasing_loan_count',
    )

    @api.depends('leasing_loan_ids')
    def _compute_leasing_loan_count(self):
        for order in self:
            order.leasing_loan_count = len(order.leasing_loan_ids)

    def action_view_leasing_schedule(self):
        """Open the leasing schedule(s) related to this PO."""
        self.ensure_one()
        loans = self.leasing_loan_ids
        if len(loans) == 1:
            return {
                'type': 'ir.actions.act_window',
                'name': _('Leasing Schedule'),
                'res_model': 'account.loan',
                'res_id': loans.id,
                'view_mode': 'form',
                'target': 'current',
            }
        return {
            'type': 'ir.actions.act_window',
            'name': _('Leasing Schedules'),
            'res_model': 'account.loan',
            'view_mode': 'list,form',
            'domain': [('id', 'in', loans.ids)],
            'target': 'current',
        }

    def action_create_leasing_schedule(self):
        """Create a new Leasing Schedule (account.loan) linked to this PO with auto-filled data."""
        self.ensure_one()
        if not self.is_leasing:
            raise models.ValidationError(_(
                "This Purchase Order is not a Leasing type. "
                "Please set the PO Type to a Leasing type first."
            ))

        qty = max(1, int(sum(self.order_line.mapped('product_qty'))))

        created_loans = self.env['account.loan']
        for i in range(qty):
            loan_vals = {
                'name': _('New Leasing %s') % (i+1) if qty > 1 else _('New Leasing'),
                'purchase_order_id': self.id,
                'amount_borrowed': self.amount_total / qty,
            }
            created_loans += self.env['account.loan'].create(loan_vals)

        return self.action_view_leasing_schedule()
