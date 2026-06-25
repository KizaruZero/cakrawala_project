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
    code = fields.Selection(
        selection=[
            ('accident', 'Accident'),
            ('non_accident', 'Non-Accident'),
        ],
        string='Code',
        required=True,
    )
