from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    """Move RUU/OTR ranges from separate masters onto each factor rule."""
    cr.execute(
        """SELECT column_name
             FROM information_schema.columns
            WHERE table_name = 'rpc_incentive_factor'
              AND column_name IN ('ruu_range_id', 'otr_range_id')"""
    )
    legacy_columns = {row[0] for row in cr.fetchall()}
    if {'ruu_range_id', 'otr_range_id'}.issubset(legacy_columns):
        cr.execute(
            """UPDATE rpc_incentive_factor factor
                  SET ruu_from = ruu.minimum,
                      ruu_to = ruu.maximum,
                      ruu_from_inclusive = ruu.minimum_inclusive,
                      ruu_to_inclusive = ruu.maximum_inclusive,
                      otr_from = otr.minimum,
                      otr_to = otr.maximum,
                      otr_from_inclusive = otr.minimum_inclusive,
                      otr_to_inclusive = otr.maximum_inclusive
                 FROM rpc_incentive_ruu_range ruu,
                      rpc_incentive_otr_range otr
                WHERE factor.ruu_range_id = ruu.id
                  AND factor.otr_range_id = otr.id"""
        )

    env = api.Environment(cr, SUPERUSER_ID, {})
    env.invalidate_all()
    env['rpc.incentive.factor']._ensure_default_rules()
