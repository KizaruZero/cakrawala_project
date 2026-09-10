# -*- coding: utf-8 -*-


def migrate(cr, version):
    """Keep one legacy approver when replacing Many2many with Many2one."""
    from odoo import api, SUPERUSER_ID

    env = api.Environment(cr, SUPERUSER_ID, {})
    cr.execute("SELECT to_regclass('rpc_approval_stage_user_rel')")
    legacy_relation_exists = cr.fetchone()[0]
    if legacy_relation_exists:
        cr.execute("""
            UPDATE rpc_approval_stage AS stage
               SET approver_id = legacy.user_id
              FROM (
                    SELECT relation.stage_id, MIN(relation.user_id) AS user_id
                      FROM rpc_approval_stage_user_rel AS relation
                      JOIN res_users AS users
                        ON users.id = relation.user_id
                     WHERE users.active
                       AND NOT users.share
                  GROUP BY relation.stage_id
                   ) AS legacy
             WHERE stage.id = legacy.stage_id
        """)
        env['rpc.approval.stage'].invalidate_model(['approver_id'])

    env['rpc.approval.stage']._ensure_default_approvers()
