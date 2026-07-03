from odoo import models, fields, api
from odoo.exceptions import ValidationError

class StockMove(models.Model):
    _inherit = 'stock.move'

    def unlink(self):
        for move in self:
            is_from_po = False

            if hasattr(move, 'purchase_line_id') and move.purchase_line_id:
                is_from_po = True

            if not is_from_po and move.picking_id:
                if hasattr(move.picking_id, 'purchase_id') and move.picking_id.purchase_id:
                    is_from_po = True

            if not is_from_po and move.origin:
                if move.origin.strip().upper().startswith('PO'):
                    is_from_po = True

            if is_from_po:
                raise ValidationError(
                    f"Tidak dapat menghapus baris produk '{move.product_id.display_name}' "
                    f"karena dokumen ini berasal dari Purchase Order.\n"
                    f"(Source: {move.origin or move.picking_id.name or '-'})"
                )

        return super().unlink()


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    custom_po_reference_id = fields.Many2one(
        'purchase.order',
        string='PO Reference',
        compute='_compute_custom_po_reference_id',
        store=False,
        help='Purchase Order yang menjadi sumber dokumen ini (computed, tidak disimpan).',
    )

    @api.depends('origin')
    def _compute_custom_po_reference_id(self):
        PurchaseOrder = self.env.get('purchase.order')

        for picking in self:
            result = False

            if hasattr(picking, 'purchase_id') and picking.purchase_id:
                result = picking.purchase_id

            elif PurchaseOrder is not None and picking.origin:
                po = PurchaseOrder.search([('name', '=', picking.origin)], limit=1)
                result = po if po else False

            picking.custom_po_reference_id = result

    def button_validate(self):
        for picking in self:
            if picking.picking_type_id.is_require_analytics_account:
                for move in picking.move_ids:
                    if move.product_id.type == 'product' or move.product_id.type == 'consu':
                        has_analytic = False
                        if hasattr(move, 'analytic_distribution') and move.analytic_distribution:
                            has_analytic = True
                        if hasattr(move, 'x_spk_analytic_distribution') and move.x_spk_analytic_distribution:
                            has_analytic = True
                        if hasattr(move, 'analytic_account_id') and move.analytic_account_id:
                            has_analytic = True
                        
                        if not has_analytic:
                            raise ValidationError(f"Analytic Account must be filled for product '{move.product_id.display_name}' because the Operation Type requires it.")
        
        return super().button_validate()
