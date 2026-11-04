"""19.0.1.0.2: jurnal koreksi nilai dan baris selisih klaim tidak membawa qty.

Sebelumnya qty move ikut tercatat di jurnal koreksi (bill telat beda harga, landed cost, dst.)
dan di baris selisih klaim credit note vendor, sehingga qty laporan Saldo Interim Valuasi
terhitung dua kali. Nilai (debit/kredit) tidak berubah; hanya kolom quantity yang dinolkan.
"""
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    cr.execute("""
        UPDATE account_move_line aml
           SET quantity = 0
          FROM account_move am
          JOIN stock_move sm ON sm.id = am.eai_rt_stock_move_id
         WHERE aml.move_id = am.id
           AND am.id IS DISTINCT FROM sm.account_move_id
           AND COALESCE(aml.quantity, 0) <> 0
    """)
    corrections = cr.rowcount
    cr.execute("""
        UPDATE account_move_line aml
           SET quantity = 0
          FROM account_move am
         WHERE aml.move_id = am.id
           AND am.move_type = 'in_refund'
           AND aml.display_type = 'cogs'
           AND aml.eai_rt_role IN ('claim', 'input', 'other')
           AND COALESCE(aml.quantity, 0) <> 0
    """)
    _logger.info("eai_stock_valuation_realtime 19.0.1.0.2: qty dinolkan pada %s baris jurnal koreksi "
                 "dan %s baris selisih klaim", corrections, cr.rowcount)
