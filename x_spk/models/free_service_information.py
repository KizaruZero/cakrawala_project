from odoo import api, fields, models
from dateutil.relativedelta import relativedelta


class FreeServiceItem(models.Model):
    _name = "free.service.item"
    _description = "Free Service Master Item"
    _order = "name asc"

    name = fields.Char(string="Name", required=True)
    description = fields.Text(string="Product Description")
    duration = fields.Integer(string="Default Duration", default=1)
    unit_of_time = fields.Selection([
        ('days', 'Days'),
        ('months', 'Months'),
        ('years', 'Years'),
    ], string="Default Unit of Time", default='months', required=True)


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
    free_service_item_id = fields.Many2one(
        "free.service.item",
        string="Free Service Item",
        required=True,
    )
    item_free = fields.Char(
        string="Item Free",
        related="free_service_item_id.name",
        store=True,
        readonly=True,
    )
    description = fields.Text(
        string="Product Description",
        related="free_service_item_id.description",
        readonly=True,
    )
    valid_from = fields.Date(
        string="Start From",
        required=True,
        default=fields.Date.today,
    )
    duration = fields.Integer(
        string="Duration",
        required=True,
        compute="_compute_period_from_item",
        store=True,
        readonly=False,
        precompute=True,
    )
    unit_of_time = fields.Selection([
        ('days', 'Days'),
        ('months', 'Months'),
        ('years', 'Years'),
    ],
        string="Unit of Time",
        required=True,
        compute="_compute_period_from_item",
        store=True,
        readonly=False,
        precompute=True,
    )

    valid_until = fields.Date(
        string="Valid Until",
        compute="_compute_valid_until",
        store=True,
    )

    @api.depends('free_service_item_id')
    def _compute_period_from_item(self):
        """Seed the period from the master item's defaults.

        Editable (readonly=False), so a value supplied for this vehicle wins; it
        is a compute rather than an onchange so imports and other non-UI writes
        pick the master defaults up too.
        """
        for rec in self:
            item = rec.free_service_item_id
            rec.duration = item.duration if item else 1
            rec.unit_of_time = item.unit_of_time if item else 'months'

    @api.depends('valid_from', 'duration', 'unit_of_time')
    def _compute_valid_until(self):
        for rec in self:
            if rec.valid_from and rec.duration:
                duration = int(rec.duration)
                if rec.unit_of_time == 'days':
                    rec.valid_until = rec.valid_from + relativedelta(days=duration)
                elif rec.unit_of_time == 'months':
                    rec.valid_until = rec.valid_from + relativedelta(months=duration)
                elif rec.unit_of_time == 'years':
                    rec.valid_until = rec.valid_from + relativedelta(years=duration)
                else:
                    rec.valid_until = False
            else:
                rec.valid_until = False


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
