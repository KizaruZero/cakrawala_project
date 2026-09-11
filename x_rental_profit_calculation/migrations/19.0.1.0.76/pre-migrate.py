# -*- coding: utf-8 -*-


def migrate(cr, version):
    """Remove the obsolete state binding from the approval-stage master."""
    cr.execute("SELECT to_regclass('rpc_approval_stage')")
    if not cr.fetchone()[0]:
        return
    cr.execute(
        'ALTER TABLE rpc_approval_stage DROP COLUMN IF EXISTS state'
    )
