{
    'name': 'Disable Create on Relational Fields',
    'version': '19.0.1.0.0',
    'summary': 'Hide "Create" / "Create and edit..." on every many2one and many2many field',
    'description': """
Master data must be created from its own menu, not on the fly from another form.

This module forces can_create=False on every editable many2one / many2many field
of every view, so the "Create", "Create and edit..." and "New" (Search More) options
disappear everywhere at once, without configuring each field in Studio.

* Exceptions per model: system parameter ``x_disable_quick_create.allowed_models``
  (comma-separated technical names, default ``stock.lot`` for receipts).
* Exceptions per user: group "Allow Create from Relational Fields".
    """,
    'category': 'Hidden/Tools',
    'license': 'LGPL-3',
    'depends': ['base'],
    'data': [
        'security/res_groups.xml',
        'data/ir_config_parameter.xml',
    ],
    'installable': True,
    'application': False,
}
