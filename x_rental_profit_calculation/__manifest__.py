## -*- coding: utf-8 -*-
{
    'name': 'Rental Profit Calculation',
    'version': '19.0.1.0.43',
    'category': 'Sales/Rental',
    'summary': 'Rental Profit Calculation (RPC) for PT Cakrawala Rentalindo Sejahtera',
    'description': """
        Module untuk mengelola Rental Profit Calculation (RPC) yang terintegrasi
        dengan CRM, Sales, Inventory, dan Accounting.

        Fitur:
        - Pembuatan dan pengelolaan dokumen RPC
        - Workflow multi-departemen (Marketing, Procurement, Operation, Finance)
        - Kalkulasi otomatis OTR, Asuransi, Resale Value
        - Tabel Funding Needs dan Gapping Costs Batas Atas/Bawah
        - Master data Wilayah, Provinsi, Wilayah Type, Asuransi Rate
        - Notifikasi antar departemen
    """,
    'author': 'Doni Hadiansyah - Xapiens Teknologi Indonesia',
    'website': 'https://xapiens.id',
    'license': 'LGPL-3',
    'depends': [
        'base',
        'mail',
        'hr',
        'crm',
        'sale_management',
        'account',
        'stock',
    ],
    'data': [
        # Security
        'security/rpc_security.xml',
        'security/ir.model.access.csv',

        # Data
        'data/rpc_sequence_data.xml',
        'data/rpc_jenis_kendaraan_data.xml',
        'data/rpc_wilayah_data.xml',
        'data/rpc_provinsi_data.xml',
        'data/rpc_wilayah_type_data.xml',
        'data/rpc_asuransi_rate_data.xml',
        'data/rpc_hierarchy_logic_data.xml',
        'data/rpc_finance_line_type_data.xml',

        # Views - Parameter/Master
        'views/rpc_wilayah_views.xml',
        'views/rpc_provinsi_views.xml',
        'views/rpc_kota_views.xml',
        'views/rpc_wilayah_type_views.xml',
        'views/rpc_asuransi_rate_views.xml',
        'views/rpc_parameter_views.xml',
        'views/rpc_funding_hierarchy_views.xml',
        'views/rpc_hierarchy_logic_views.xml',
        'views/rpc_finance_line_type_views.xml',
        'views/rpc_logic_table_views.xml',

        # Views - Main
        'views/rpc_document_views.xml',
        'views/rpc_menu_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'x_rental_profit_calculation/static/src/scss/rpc_document.scss',
        ],
    },
    'installable': True,
    'application': True,
    'auto_install': False,
}
