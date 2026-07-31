{
    'name': 'Contact Enhanced',
    'version': '19.0.1.0.1',
    'category': 'Fleet Custom',
    'summary': 'Enhance Contact module with company and legal information',
    'description': """
        This module extends the standard Odoo Contact module with:
        - Company Information fields (bidang usaha, kepemilikan, etc.)
        - Legal & Compliance Checklist with attachment management
        - Two new tabs in contact form view
    """,
    'author': 'Your Company',
    'depends': ['base', 'contacts', 'account'],
    'data': [
        'security/ir.model.access.csv',
        'views/res_partner_views.xml',
    ],
    'installable': True,
    'auto_install': False,
    'application': False,
}
