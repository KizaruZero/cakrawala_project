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
