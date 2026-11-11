{
    'name': 'Payment Custom - Multi Account Write-Off',
    'version': '19.0.1.0.0',
    'summary': 'Post the payment difference ("Mark as fully paid") to several accounts',
    'description': """
Payment Difference Multi Account
================================

Pada wizard **Pay** (invoice / vendor bill), opsi *Payment Difference* ->
*Mark as fully paid* bawaan Odoo hanya bisa diposting ke satu account.

Modul ini mengganti field "Post Difference In" + "Label" dengan sebuah tabel
(Account, Label, Analytic, Amount) sehingga selisih pembayaran bisa dipecah
ke beberapa account sekaligus.

* Baris baru otomatis terisi sisa selisih yang belum dialokasikan.
* Total tabel wajib sama dengan Payment Difference sebelum payment dibuat.
    """,
    'author': 'Doni Hadiansyah - Xapiens Teknologi Indonesia',
    'website': 'https://xapiens.id',
    'category': 'Accounting/Accounting',
    'license': 'LGPL-3',
    'depends': ['account'],
    'data': [
        'security/ir.model.access.csv',
        'wizard/account_payment_register_views.xml',
    ],
    'installable': True,
    'application': False,
}
