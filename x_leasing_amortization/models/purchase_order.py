# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError
from odoo.tools import SQL, float_is_zero


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
    leasing_agreement = fields.Char(
        string='Leasing Agreement',
        tracking=True,
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
        self.check_access('read')
        self.env['account.loan'].check_access('create')
        if self.company_id not in self.env.companies:
            raise ValidationError(_('Select the Purchase Order company before creating Leasing Schedules.'))
        self.flush_recordset()
        self.env.cr.execute(SQL('SELECT id FROM purchase_order WHERE id IN %s ORDER BY id FOR UPDATE', tuple(self.ids)))
        self.env.cr.execute(SQL('UPDATE purchase_order SET write_date = write_date WHERE id IN %s', tuple(self.ids)))
        self.invalidate_recordset(['leasing_loan_ids'])
        if not self.is_leasing:
            raise ValidationError(_(
                "This Purchase Order is not a Leasing type. "
                "Please set the PO Type to a Leasing type first."
            ))

        # 1. Kumpulkan semua kendaraan yang sudah di-receive untuk PO ini dan petakan ke PO line
        received_vehicles = self.env['fleet.vehicle']
        vehicle_to_line = {}
        for picking in self.picking_ids.filtered(lambda p: p.state == 'done'):
            for move in picking.move_ids:
                for move_line in move.move_line_ids:
                    if move_line.lot_id and move_line.lot_id.fleet_vehicle_id:
                        vehicle = move_line.lot_id.fleet_vehicle_id
                        received_vehicles |= vehicle
                        if move.purchase_line_id:
                            vehicle_to_line[vehicle.id] = move.purchase_line_id.id

        existing_loans = self.env['account.loan'].search([('purchase_order_id', '=', self.id)])
        existing_vehicles = existing_loans.mapped('vehicle_id')

        # 3. Cari kendaraan yang belum dibuatkan Leasing Schedule
        unmapped_vehicles = list(received_vehicles - existing_vehicles)

        vehicle_lines = self.order_line.filtered(lambda l: l.product_id.type != 'service' and l.product_qty > 0)
        if not vehicle_lines:
            raise ValidationError(_("Tidak ada baris kendaraan pada Purchase Order ini."))
        if vehicle_lines.filtered(lambda line: not float_is_zero(line.product_qty - round(line.product_qty), precision_digits=6)):
            raise ValidationError(_('Quantity kendaraan harus berupa unit utuh untuk membuat satu Leasing Schedule per unit.'))

        created_loans = self.env['account.loan']
        start_index = len(existing_loans) + 1
        
        # Buat Leasing Schedule per PO line
        for line in vehicle_lines:
            # Hitung berapa loan yang sudah ada untuk line ini
            # Asumsi: Jika loan punya vehicle_id, cek apakah vehicle_id itu milik line ini.
            # Atau cek jika loan punya purchase_line_id == line.id
            line_loans = existing_loans.filtered(
                lambda l: (l.purchase_line_id and l.purchase_line_id.id == line.id) or 
                          (l.vehicle_id and vehicle_to_line.get(l.vehicle_id.id) == line.id)
            )
            
            to_create = int(line.product_qty) - len(line_loans)
            
            for j in range(to_create):
                # Cari vehicle yang belum ter-map dan milik line ini
                vehicle_id = False
                for v in unmapped_vehicles:
                    if vehicle_to_line.get(v.id) == line.id:
                        vehicle_id = v.id
                        unmapped_vehicles.remove(v)
                        break
                
                # Jika tidak ada vehicle_id yang spesifik ke line ini, ambil sembarang yang cocok dengan product
                if not vehicle_id:
                    for v in unmapped_vehicles:
                        if hasattr(v, 'model_id') and v.model_id.product_id and v.model_id.product_id.id == line.product_id.id:
                            vehicle_id = v.id
                            unmapped_vehicles.remove(v)
                            break
                            
                # Fallback, ambil yang mana saja
                if not vehicle_id and unmapped_vehicles:
                    vehicle_id = unmapped_vehicles.pop(0).id

                loan_vals = {
                    'name': _('New Leasing %s') % start_index,
                    'purchase_order_id': self.id,
                    'purchase_line_id': line.id,
                    'vehicle_id': vehicle_id,
                    'vehicle_variant': line.name or line.product_id.display_name,
                    'company_id': self.company_id.id,
                    'bank_id': self.leasing_partner_id.id,
                    'vendor_id': self.partner_id.id,
                    # The subtotal already includes fixed/percentage discount
                    # and removes included taxes. Do not subtract discount twice
                    # or copy a whole multi-unit line amount to every unit.
                    'harga_otr': line.price_subtotal / line.product_qty,
                }
                created_loans += self.env['account.loan'].create(loan_vals)
                start_index += 1
                
        if not created_loans:
            raise ValidationError(_("Leasing Schedule sudah dibuat untuk seluruh quantity pesanan."))

        return self.action_view_leasing_schedule()
