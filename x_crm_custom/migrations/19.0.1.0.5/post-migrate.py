# -*- coding: utf-8 -*-


def migrate(cr, version):
    """Backfill linked RPCs without overwriting values already entered."""
    cr.execute("""
        UPDATE rpc_document AS rpc
           SET existing_unit = lead.existing_fleet
          FROM crm_lead AS lead
         WHERE rpc.crm_lead_id = lead.id
           AND COALESCE(rpc.existing_unit, 0) = 0
           AND COALESCE(lead.existing_fleet, 0) != 0
    """)
