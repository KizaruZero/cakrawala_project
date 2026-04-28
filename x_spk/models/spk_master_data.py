from odoo import fields, models


class SPKExecutionType(models.Model):
    _name = "spk.execution.type"
    _description = "SPK Execution Type"
    _order = "sequence, name"

    name = fields.Char(string="Name", required=True)
    code = fields.Char(string="Code", required=True, index=True)
    sequence = fields.Integer(string="Sequence", default=10)
    active = fields.Boolean(string="Active", default=True)

class SPKMaintenanceType(models.Model):
    _name = "spk.maintenance.type"
    _description = "SPK Maintenance Type"
    _order = "sequence, name"

    name = fields.Char(string="Name", required=True)
    code = fields.Char(string="Code", required=True, index=True)
    sequence = fields.Integer(string="Sequence", default=10)
    active = fields.Boolean(string="Active", default=True)

