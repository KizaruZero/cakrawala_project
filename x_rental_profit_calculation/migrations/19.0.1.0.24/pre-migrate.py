def migrate(cr, version):
    # Finance lines were manually maintained before 19.0.1.0.24. They are
    # replaced by rows generated from the Finance Cashflow Type master.
    cr.execute('DELETE FROM rpc_document_finance_line')
