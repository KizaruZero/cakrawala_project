from odoo import models, fields

class BastkMasterDescription(models.Model):
    _name = 'bastk.master.description'
    _description = 'BASTK Master Description'
    _order = 'item_type_id, id'

    name = fields.Char(required=True)
    item_type_id = fields.Many2one('bastk.item.type', string='BASTK Item Category', ondelete='set null')
    selection_ids = fields.Many2many(
        'bastk.item.selection',
        'bastk_master_desc_selection_rel',
        'master_id',
        'selection_id',
        string='Selections'
    )
    type = fields.Selection([
        ('keluar', 'Keluar'),
        ('masuk', 'Masuk'),
        ('both', 'Both'),
    ], required=True, default='both')
    active = fields.Boolean(string="Active", default=True)

    def unlink(self):
        """Pastikan snapshot nama dan kategori tersimpan di bastk.description sebelum master dihapus."""
        if self:
            lines = self.env['bastk.description'].sudo().search([
                ('checklist_id', 'in', self.ids),
            ])
            for line in lines:
                vals = {}
                master_name = line.checklist_id.name
                if master_name and not line.name:
                    vals['name'] = master_name
                if master_name and not line.item_display_name:
                    vals['item_display_name'] = master_name
                if line.checklist_id.item_type_id and not line.item_type_id:
                    vals['item_type_id'] = line.checklist_id.item_type_id.id
                if vals:
                    line.write(vals)
        return super().unlink()
