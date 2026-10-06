# -*- coding: utf-8 -*-
from odoo import api, fields, models


class StockReturnPickingLine(models.TransientModel):
    _inherit = 'stock.return.picking.line'

    license_plate = fields.Char(
        string='License Plate',
        compute='_compute_license_plate',
        readonly=True,
    )

    @api.depends('move_id', 'move_id.move_line_ids', 'move_id.move_line_ids.initial_license_plate', 'move_id.move_line_ids.lot_id')
    def _compute_license_plate(self):
        for line in self:
            plates = []
            if line.move_id:
                for ml in line.move_id.move_line_ids:
                    plate = (
                        ml.initial_license_plate
                        or (ml.lot_id and (getattr(ml.lot_id, 'current_license_plate', False) or getattr(ml.lot_id, 'initial_license_plate', False)))
                        or (ml.lot_id and getattr(ml.lot_id, 'fleet_vehicle_id', False) and ml.lot_id.fleet_vehicle_id.license_plate)
                    )
                    if plate and plate not in plates:
                        plates.append(str(plate).strip())
                if not plates and line.move_id.initial_license_plate:
                    for p in line.move_id.initial_license_plate.split('\n'):
                        p_str = p.strip()
                        if p_str and p_str not in plates:
                            plates.append(p_str)
            line.license_plate = ', '.join(plates) if plates else ''
