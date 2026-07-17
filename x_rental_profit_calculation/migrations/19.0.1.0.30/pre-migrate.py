MODULE = 'x_rental_profit_calculation'

HIERARCHIES = (
    ('hierarchy_logic_finansial', 'FINANSIAL'),
    ('hierarchy_logic_biaya_variabel_kendaraan', 'BIAYA VARIABEL KENDARAAN'),
    ('hierarchy_logic_fitur', 'FITUR'),
    ('hierarchy_logic_marketing_komisi', 'MARKETING & KOMISI'),
)

COST_GROUP_CODES = (
    ('cost_group_code_f01', 'F01'),
    ('cost_group_code_f02', 'F02'),
    ('cost_group_code_f03', 'F03'),
    ('cost_group_code_bvk01', 'BVK01'),
    ('cost_group_code_bvk02', 'BVK02'),
    ('cost_group_code_bvk03', 'BVK03'),
    ('cost_group_code_bvk04', 'BVK04'),
    ('cost_group_code_ft01', 'FT01'),
    ('cost_group_code_ft02', 'FT02'),
    ('cost_group_code_ft03', 'FT03'),
    ('cost_group_code_ft04', 'FT04'),
    ('cost_group_code_mk01', 'MK01'),
    ('cost_group_code_mk02', 'MK02'),
    ('cost_group_code_mk03', 'MK03'),
    ('cost_group_code_mk04', 'MK04'),
)

COST_GROUP_NAMES = (
    ('cost_group_name_total_down_payment', 'TOTAL DOWN PAYMENT'),
    ('cost_group_name_selisih_sewa_angsuran', 'SELISIH SEWA DGN ANGSURAN'),
    ('cost_group_name_terms_of_payment', 'TERMS OF PAYMENT'),
    ('cost_group_name_stnk', 'STNK'),
    ('cost_group_name_asuransi', 'ASURANSI'),
    ('cost_group_name_service', 'SERVICE'),
    ('cost_group_name_replacement_car', 'REPLACEMENT CAR'),
    ('cost_group_name_management_fee', 'MANAGEMENT FEE'),
    ('cost_group_name_own_risk', 'OWN RISK'),
    ('cost_group_name_bank_garansi', 'BANK GARANSI'),
    ('cost_group_name_asuransi_jiwa', 'ASURANSI JIWA'),
    ('cost_group_name_pic_internal', 'PIC INTERNAL'),
    ('cost_group_name_infrastruktur', 'INFRASTRUKTUR'),
    ('cost_group_name_komisi_proyek', 'KOMISI PROYEK'),
    ('cost_group_name_lainnya', 'LAINNYA'),
)

PAYMENT_SCHEDULES = (
    ('payment_schedule_di_depan', 'DI DEPAN', 'cost_group_name_total_down_payment'),
    ('payment_schedule_tiap_bulan', 'TIAP BULAN', 'cost_group_name_selisih_sewa_angsuran'),
    ('payment_schedule_terms_of_payment_tiap_bulan', 'TIAP BULAN', 'cost_group_name_terms_of_payment'),
    ('payment_schedule_di_depan_tiap_tahun', 'DI DEPAN TIAP TAHUN', 'cost_group_name_stnk'),
    ('payment_schedule_60_hari_tiap_tahun', '60 HARI TIAP TAHUN', 'cost_group_name_asuransi'),
    ('payment_schedule_service_tiap_bulan', 'TIAP BULAN', 'cost_group_name_service'),
    ('payment_schedule_replacement_car_tiap_bulan', 'TIAP BULAN', 'cost_group_name_replacement_car'),
    ('payment_schedule_management_fee_di_depan_tiap_tahun', 'DI DEPAN TIAP TAHUN', 'cost_group_name_management_fee'),
    ('payment_schedule_own_risk_tiap_bulan', 'TIAP BULAN', 'cost_group_name_own_risk'),
    ('payment_schedule_di_depan_lumpsum', 'DI DEPAN LUMPSUM', 'cost_group_name_bank_garansi'),
    ('payment_schedule_asuransi_jiwa_60_hari_tiap_tahun', '60 HARI TIAP TAHUN', 'cost_group_name_asuransi_jiwa'),
    ('payment_schedule_pic_internal_tiap_bulan', 'TIAP BULAN', 'cost_group_name_pic_internal'),
    ('payment_schedule_infrastruktur_di_depan_lumpsum', 'DI DEPAN LUMPSUM', 'cost_group_name_infrastruktur'),
    ('payment_schedule_komisi_proyek_di_depan_lumpsum', 'DI DEPAN LUMPSUM', 'cost_group_name_komisi_proyek'),
    ('payment_schedule_lainnya_tiap_bulan', 'TIAP BULAN', 'cost_group_name_lainnya'),
)

LEGACY_PAYMENT_SCHEDULE_XMLIDS = {
    'payment_schedule_di_depan',
    'payment_schedule_tiap_bulan',
    'payment_schedule_di_depan_tiap_tahun',
    'payment_schedule_60_hari_tiap_tahun',
    'payment_schedule_di_depan_lumpsum',
}

LOGIC_LINES = (
    ('hierarchy_logic_line_f01', 'cost_group_code_f01'),
    ('hierarchy_logic_line_f02', 'cost_group_code_f02'),
    ('hierarchy_logic_line_f03', 'cost_group_code_f03'),
    ('hierarchy_logic_line_bvk01', 'cost_group_code_bvk01'),
    ('hierarchy_logic_line_bvk02', 'cost_group_code_bvk02'),
    ('hierarchy_logic_line_bvk03', 'cost_group_code_bvk03'),
    ('hierarchy_logic_line_bvk04', 'cost_group_code_bvk04'),
    ('hierarchy_logic_line_ft01', 'cost_group_code_ft01'),
    ('hierarchy_logic_line_ft02', 'cost_group_code_ft02'),
    ('hierarchy_logic_line_ft03', 'cost_group_code_ft03'),
    ('hierarchy_logic_line_ft04', 'cost_group_code_ft04'),
    ('hierarchy_logic_line_mk01', 'cost_group_code_mk01'),
    ('hierarchy_logic_line_mk02', 'cost_group_code_mk02'),
    ('hierarchy_logic_line_mk03', 'cost_group_code_mk03'),
    ('hierarchy_logic_line_mk04', 'cost_group_code_mk04'),
)


def _bind_xmlid(cr, xmlid_name, model, res_id):
    cr.execute(
        """
        INSERT INTO ir_model_data (module, name, model, res_id, noupdate)
        VALUES (%s, %s, %s, %s, TRUE)
        ON CONFLICT (module, name)
        DO UPDATE SET
            model = EXCLUDED.model,
            res_id = EXCLUDED.res_id,
            noupdate = TRUE
        """,
        (MODULE, xmlid_name, model, res_id),
    )


def _xmlid_res_id(cr, xmlid_name):
    cr.execute(
        """
        SELECT res_id
          FROM ir_model_data
         WHERE module = %s
           AND name = %s
         LIMIT 1
        """,
        (MODULE, xmlid_name),
    )
    row = cr.fetchone()
    return row[0] if row else None


def _find_by_name(cr, table, name):
    cr.execute(
        f"""
        SELECT id
          FROM {table}
         WHERE LOWER(name) = LOWER(%s)
         ORDER BY id
         LIMIT 1
        """,
        (name,),
    )
    row = cr.fetchone()
    return row[0] if row else None


def _column_exists(cr, table, column):
    cr.execute(
        """
        SELECT 1
          FROM information_schema.columns
         WHERE table_schema = current_schema()
           AND table_name = %s
           AND column_name = %s
         LIMIT 1
        """,
        (table, column),
    )
    return bool(cr.fetchone())


def _bind_named_records(cr, seeds, table, model):
    for xmlid_name, name in seeds:
        res_id = _find_by_name(cr, table, name)
        if res_id:
            _bind_xmlid(cr, xmlid_name, model, res_id)


def _bind_payment_schedules(cr):
    table = 'rpc_hierarchy_logic_payment_schedule'
    relation_exists = _column_exists(cr, table, 'cost_group_name_id')

    for xmlid_name, name, cost_group_name_xmlid in PAYMENT_SCHEDULES:
        res_id = None
        cost_group_name_id = _xmlid_res_id(cr, cost_group_name_xmlid)
        if relation_exists and cost_group_name_id:
            cr.execute(
                f"""
                SELECT id
                  FROM {table}
                 WHERE LOWER(name) = LOWER(%s)
                   AND cost_group_name_id = %s
                 ORDER BY id
                 LIMIT 1
                """,
                (name, cost_group_name_id),
            )
            row = cr.fetchone()
            res_id = row[0] if row else None

        # Before the hierarchy-chain change there were only five shared
        # payment-schedule records. Bind those legacy XML IDs by name; the
        # remaining schedule records will be created normally by XML data.
        if not res_id and xmlid_name in LEGACY_PAYMENT_SCHEDULE_XMLIDS:
            res_id = _find_by_name(cr, table, name)

        if res_id:
            _bind_xmlid(
                cr,
                xmlid_name,
                'rpc.hierarchy.logic.payment.schedule',
                res_id,
            )


def _bind_logic_lines(cr):
    for xmlid_name, cost_group_code_xmlid in LOGIC_LINES:
        cost_group_code_id = _xmlid_res_id(cr, cost_group_code_xmlid)
        if not cost_group_code_id:
            continue
        cr.execute(
            """
            SELECT id
              FROM rpc_hierarchy_logic
             WHERE cost_group_code_id = %s
             ORDER BY id
             LIMIT 1
            """,
            (cost_group_code_id,),
        )
        row = cr.fetchone()
        if row:
            _bind_xmlid(cr, xmlid_name, 'rpc.hierarchy.logic', row[0])


def migrate(cr, version):
    """Bind all Hierarchy Logic seed XML IDs to existing master data."""
    _bind_named_records(
        cr,
        HIERARCHIES,
        'rpc_hierarchy_logic_hierarchy',
        'rpc.hierarchy.logic.hierarchy',
    )
    _bind_named_records(
        cr,
        COST_GROUP_CODES,
        'rpc_hierarchy_logic_cost_group_code',
        'rpc.hierarchy.logic.cost.group.code',
    )
    _bind_named_records(
        cr,
        COST_GROUP_NAMES,
        'rpc_hierarchy_logic_cost_group_name',
        'rpc.hierarchy.logic.cost.group.name',
    )
    _bind_payment_schedules(cr)
    _bind_logic_lines(cr)
