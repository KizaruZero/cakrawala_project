from odoo import SUPERUSER_ID, api


LEGACY_PURCHASE_FIELDS = (
    ('harga_otr', 'harga_otr', None),
    ('discount', 'discount', 'discount_dikapitalisasi'),
    ('cashback', 'cashback', 'cashback_dikapitalisasi'),
    (
        'biaya_ekspedisi',
        'biaya_ekspedisi',
        'biaya_ekspedisi_dikapitalisasi',
    ),
)

OTR_FIELDS = ('otr_final', 'otr_leasing', 'otr_asuransi')
RUU_FIELDS = (
    'ruu_gross',
    'ruu_netto',
    'ruu_gross_batas_bawah',
    'ruu_netto_batas_bawah',
)


def _copy_legacy_purchase_value(cr, line_type, amount_field, capitalized_field):
    capitalized_sql = ''
    if capitalized_field:
        capitalized_sql = f"""
            , {capitalized_field} = CASE
                WHEN COALESCE(document.{amount_field}, 0) = 0
                THEN CASE WHEN legacy.capitalized THEN 'yes' ELSE 'no' END
                ELSE document.{capitalized_field}
              END
        """

    cr.execute(
        f"""
        WITH legacy AS (
            SELECT DISTINCT ON (document_id)
                   document_id,
                   COALESCE(amount, 0) AS amount,
                   capitalized
              FROM rpc_document_purchase_line
             WHERE line_type = %s
             ORDER BY document_id, sequence, id
        )
        UPDATE rpc_document AS document
           SET {amount_field} = CASE
                   WHEN COALESCE(document.{amount_field}, 0) = 0
                   THEN legacy.amount
                   ELSE document.{amount_field}
               END
               {capitalized_sql}
          FROM legacy
         WHERE document.id = legacy.document_id
        """,
        (line_type,),
    )


def _schedule_recompute(env, records, field_names):
    for field_name in field_names:
        env.add_to_compute(records._fields[field_name], records)
    records._recompute_recordset(field_names)


def migrate(cr, version):
    """Move legacy purchasing rows to rpc.document and refresh formulas."""
    for field_mapping in LEGACY_PURCHASE_FIELDS:
        _copy_legacy_purchase_value(cr, *field_mapping)

    cr.execute(
        """
        DELETE FROM rpc_document_purchase_line
         WHERE line_type IN (
             'harga_otr', 'discount', 'cashback', 'biaya_ekspedisi'
         )
        """
    )

    env = api.Environment(cr, SUPERUSER_ID, {})
    documents = env['rpc.document'].with_context(active_test=False).search([])
    documents.invalidate_recordset([
        'harga_otr',
        'discount',
        'discount_dikapitalisasi',
        'cashback',
        'cashback_dikapitalisasi',
        'biaya_ekspedisi',
        'biaya_ekspedisi_dikapitalisasi',
        'purchase_line_ids',
    ])

    _schedule_recompute(env, documents, OTR_FIELDS)
    _schedule_recompute(env, documents, RUU_FIELDS)

    finance_lines = env['rpc.document.finance.line'].search([])
    _schedule_recompute(env, finance_lines, ('batas_atas', 'batas_bawah'))

    logic_documents = documents.filtered(
        lambda document: document.state in ('finance_done', 'approved')
    )
    logic_documents._generate_logic_table_lines()

