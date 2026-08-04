from odoo import models, fields

class FleetEngineCategory(models.Model):
    _name = "fleet.engine.category"
    _description = "Engine Category"

    name = fields.Char(string="Name", required=True)

class FleetDrivetrainCategory(models.Model):
    _name = "fleet.drivetrain.category"
    _description = "Drive Train Category"

    name = fields.Char(string="Name", required=True)

class FleetTransmission(models.Model):
    _name = "fleet.transmission"
    _description = "Transmission Type"

    name = fields.Char(string="Name", required=True)
