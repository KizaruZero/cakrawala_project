# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


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
            raise ValidationError(_(
                "This Purchase Order is not a Leasing type. "
                "Please set the PO Type to a Leasing type first."
            ))

        # 1. Kumpulkan semua kendaraan yang sudah di-receive untuk PO ini
        received_vehicles = self.env['fleet.vehicle']
        for picking in self.picking_ids.filtered(lambda p: p.state == 'done'):
            for move_line in picking.move_line_ids:
                if move_line.lot_id and move_line.lot_id.fleet_vehicle_id:
                    received_vehicles |= move_line.lot_id.fleet_vehicle_id

        # 2. Kumpulkan semua kendaraan yang sudah terikat pada Leasing Schedule PO ini
        existing_loans = self.env['account.loan'].search([('purchase_order_id', '=', self.id)])
        existing_vehicles = existing_loans.mapped('vehicle_id')

        # 3. Cari kendaraan yang belum dibuatkan Leasing Schedule
        unmapped_vehicles = received_vehicles - existing_vehicles

        # 4. Validasi jika tidak ada kendaraan sisa
        if not unmapped_vehicles:
            if not received_vehicles:
                raise ValidationError(_("Leasing Schedule belum dapat dibuat karena belum ada quantity/kendaraan yang diterima."))
            else:
                raise ValidationError(_("Leasing Schedule sudah dibuat untuk seluruh quantity yang telah diterima."))

        # 5. Hitung nominal pinjaman per jadwal berdasarkan total quantity PO awal agar pembagian rata
        ordered_qty = max(1, int(sum(self.order_line.mapped('product_qty'))))
        amount_borrowed_per_vehicle = self.amount_total / ordered_qty

        # 6. Buat Leasing Schedule baru untuk setiap kendaraan yang belum memiliki jadwal
        created_loans = self.env['account.loan']
        start_index = len(existing_loans) + 1

        for i, vehicle in enumerate(unmapped_vehicles):
            loan_vals = {
                'name': _('New Leasing %s') % (start_index + i),
                'purchase_order_id': self.id,
                'amount_borrowed': amount_borrowed_per_vehicle,
                'vehicle_id': vehicle.id,
            }
            created_loans += self.env['account.loan'].create(loan_vals)

        return self.action_view_leasing_schedule()
