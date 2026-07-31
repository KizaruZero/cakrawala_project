def migrate(cr, version):
    """Drop the old free-text Sub Type column after converting
    fleet.vehicle.sub_type (Char) to sub_type_id (Many2one to the new master).

    The field held no data in production, so nothing is migrated over; the old
    column is simply removed to keep the schema clean.
    """
    cr.execute(
        """
        ALTER TABLE fleet_vehicle
         DROP COLUMN IF EXISTS sub_type
        """
    )
