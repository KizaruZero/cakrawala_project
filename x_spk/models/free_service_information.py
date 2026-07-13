from odoo import _, api, fields, models
from dateutil.relativedelta import relativedelta


class FreeServiceItem(models.Model):
    _name = "free.service.item"
    _description = "Free Service Master Item"
    _order = "name asc"

    name = fields.Char(string="Name", required=True)
    product_id = fields.Many2one("product.product", string="Product/Item")
    description = fields.Text(string="Description", compute="_compute_description", store=True, readonly=False)
    duration = fields.Integer(string="Default Duration", default=1)
    unit_of_time = fields.Selection([
        ('days', 'Days'),
        ('months', 'Months'),
        ('years', 'Years'),
    ], string="Default Unit of Time", default='months', required=True)

    @api.depends('product_id')
    def _compute_description(self):
        for rec in self:
            if rec.product_id and not rec.description:
                rec.description = rec.product_id.description_sale or rec.product_id.display_name


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
    product_id = fields.Many2one(
        "product.product",
        related="free_service_item_id.product_id",
        string="Product/Item",
        readonly=True,
    )
    description = fields.Text(
        string="Description",
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
        default=1,
    )
    unit_of_time = fields.Selection([
        ('days', 'Days'),
        ('months', 'Months'),
        ('years', 'Years'),
    ], string="Unit of Time", default='months', required=True)

    valid_until = fields.Date(
        string="Valid Until",
        compute="_compute_valid_until",
        store=True,
    )

    @api.onchange('free_service_item_id')
    def _onchange_free_service_item_id(self):
        if self.free_service_item_id:
            self.duration = self.free_service_item_id.duration
            self.unit_of_time = self.free_service_item_id.unit_of_time

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
