from odoo import models, fields


class BakCategory(models.Model):
    """
    TASK 10A – BAK Category master data.
    Classifies a BAK record as either an Accident or Non-Accident event.
    """
    _name = 'bak.category'
    _description = 'BAK Category'
    _order = 'sequence, name'

    name = fields.Char(string='Category Name', required=True)
    sequence = fields.Integer(string='Sequence', default=10)
    active = fields.Boolean(string='Active', default=True, help="Set active to false to hide the category without removing it.")
    description = fields.Text(string='Description')
    maintenance_type_id = fields.Many2one(
        'spk.maintenance.type',
        string='Maintenance Type (SPK)',
        ondelete='set null',
        help='Linked SPK Maintenance Type. '
             'Jika maintenance type ini memiliki is_on_risk=True, '
             'maka BAK kategori ini otomatis Own Risk, dan saat Create SPK '
             'akan menerapkan flag Own Risk.',
    )
    on_risk = fields.Boolean(
        string='Own Risk Mode',
        related='maintenance_type_id.is_on_risk',
        store=True,
        readonly=True,
        help='Otomatis True jika Maintenance Type yang dipilih memiliki is_on_risk=True. '
             'Tidak bisa diubah manual.',
    )

    code = fields.Selection(
        selection=[
            ('accident', 'Accident'),
            ('non_accident', 'Non-Accident'),
        ],
        string='Code',
        required=True,
    )
