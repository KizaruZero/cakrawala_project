"""
Migration 19.0.1.0.1 — pre-migrate

1. Drop deprecated `approver_stage` from `fleet_spk`
   (old hardcoded 3-level Selection, replaced by unlimited sequence-based tracking)

2. Drop `date_valid_from` / `date_valid_to` from `spk_approval_matrix_line`
   (main approver has no time restriction; only delegate has validity period)
"""


def migrate(cr, version):
    cr.execute("""
        ALTER TABLE fleet_spk
        DROP COLUMN IF EXISTS approver_stage
    """)

    cr.execute("""
        ALTER TABLE spk_approval_matrix_line
        DROP COLUMN IF EXISTS date_valid_from,
        DROP COLUMN IF EXISTS date_valid_to
    """)
