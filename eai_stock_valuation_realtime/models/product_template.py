from odoo import models


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    def write(self, vals):
        if 'categ_id' not in vals:
            return super().write(vals)
        old_flag = {t.id: t.categ_id.eai_rt_enabled for t in self}
        res = super().write(vals)
        # Produk yang baru masuk ke kategori bertanda: transaksi lama tidak dijurnal ulang.
        moved_in = self.filtered(lambda t: t.categ_id.eai_rt_enabled and not old_flag.get(t.id))
        if moved_in:
            self.env['stock.move']._eai_rt_mark_as_posted(moved_in.with_context(active_test=False).product_variant_ids)
        return res
