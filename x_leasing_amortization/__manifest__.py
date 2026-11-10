{
    'name': 'Leasing Amortization Schedule',
    'version': '19.0.1.0.20',
    'category': 'Accounting/Accounting',
    'summary': 'Leasing Amortization Schedule integrated with Purchase Order',
    'description': """
Leasing Amortization Schedule (Tabel Angsuran)
===============================================
Extends the base Odoo Loan module (account_loans) with:
- Leasing-specific header fields (Agreement No, Bank, Vehicle info, etc.)
- Auto-fill from Purchase Order (Vendor, PO Number, Total Hutang, DP, Installment)
- Payment Date tracking on amortization schedule lines
- Smart Button on PO form to navigate to Leasing Schedule
- Manual Generate Vendor Bill per schedule line
- Two-way Flat/Effective conversion with canonical ADDM/Arrears effective allocation
- Principal-only early settlement Vendor Bill from remaining installments
    """,
    'author': 'Cakrawala',
    'depends': [
        'account_loans',
        'purchase',
        'purchase_stock',
        'purchase_order_lines_discount',
        'fleet',
        'x_stock_asset_receipt',
        'x_fleet_document',
        'purchase_down_payment',
        'x_purchase_order_approval',
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/ir_cron_data.xml',
        'data/ir_sequence_data.xml',
        'wizard/leasing_payment_wizard_views.xml',
        'views/account_loan_views.xml',
        'views/flat_schedule_views.xml',
        'views/effective2_schedule_views.xml',
        'wizard/leasing_schedule_import_views.xml',
        'views/interest_conversion_views.xml',
        'views/purchase_order_views.xml',
        'views/fleet_vehicle_views.xml',
        'views/account_move_views.xml',
        'views/leasing_simulation_views.xml',
    ],
    'installable': True,
    'external_dependencies': {'python': ['openpyxl']},
    'auto_install': False,
    'application': False,
    'license': 'LGPL-3',
}
