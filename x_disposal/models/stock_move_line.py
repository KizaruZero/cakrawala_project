from odoo import api, fields, models


class StockMoveLine(models.Model):
    _inherit = "stock.move.line"

    x_disposal_is_delivery = fields.Boolean(
        string="Is Disposal Delivery",
        related="move_id.x_disposal_is_delivery",
        store=False,
    )

    @api.onchange("lot_id", "quant_id")
    def _onchange_disposal_lot_id_load_vehicle_fields(self):
        for line in self:
            lot = line.lot_id or line.quant_id.lot_id
            if not line.x_disposal_is_delivery or not lot:
                continue
            line.initial_license_plate = lot.initial_license_plate
            line.chassis_number = lot.chassis_number
            line.engine_number = lot.engine_number

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._sync_disposal_vehicle_fields_from_lot()
        return records

    def write(self, vals):
        res = super().write(vals)
        if {"lot_id", "quant_id"} & set(vals):
            self._sync_disposal_vehicle_fields_from_lot()
        return res

    def _sync_disposal_vehicle_fields_from_lot(self):
        for line in self.filtered(lambda rec: rec.x_disposal_is_delivery and (rec.lot_id or rec.quant_id.lot_id)):
            lot = line.lot_id or line.quant_id.lot_id
            values = {
                "initial_license_plate": lot.initial_license_plate or False,
                "chassis_number": lot.chassis_number or False,
                "engine_number": lot.engine_number or False,
            }
            if any(line[field_name] != value for field_name, value in values.items()):
                super(StockMoveLine, line).write(values)
