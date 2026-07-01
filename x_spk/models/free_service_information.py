from odoo import fields, models


class FleetVehicleFreeService(models.Model):
    _name = "fleet.vehicle.free.service"
    _description = "Fleet Vehicle Free Service Information"
    _order = "valid_until desc, id desc"

    vehicle_id = fields.Many2one(
        "fleet.vehicle",
        string="Fleet Vehicle",
        required=True,
        ondelete="cascade",
        index=True,
    )
    item_free = fields.Char(
        string="Item Free",
        required=True,
    )
    description = fields.Text(
        string="Description",
    )
    duration = fields.Char(
        string="Duration",
        required=True,
    )
    valid_until = fields.Date(
        string="Valid Until",
        required=True,
    )


class FleetVehicle(models.Model):
    _inherit = "fleet.vehicle"

    free_service_ids = fields.One2many(
        "fleet.vehicle.free.service",
        "vehicle_id",
        string="Free Service Information",
    )


class FleetSPK(models.Model):
    _inherit = "fleet.spk"

    free_service_info_ids = fields.One2many(
        related="vehicle_id.free_service_ids",
        string="Free Service Information",
        readonly=True,
    )
