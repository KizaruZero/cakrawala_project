from odoo import models
from odoo.exceptions import ValidationError

class StockMove(models.Model):
    _inherit = 'stock.move'

    def unlink(self):
        for record in self:
            if record.purchase_line_id or (record.picking_id and record.picking_id.purchase_id):
                raise ValidationError("Akses Ditolak! Product line yang berasal dari Purchase Order (PO) tidak dapat dihapus.")
        
        return super(StockMove, self).unlink()