from odoo import _, api, models, fields
from odoo.exceptions import ValidationError

class FleetServiceType(models.Model):
    _inherit = 'fleet.service.type'

    is_license_plate = fields.Boolean(string="Is License Plate", default=True)
    is_bpkb = fields.Boolean(
        string="Is BPKB",
        help="BPKB documents have no expiration date, so they never expire nor send expiry reminders.",
    )
    default_product_ids = fields.Many2many(
        'product.product',
        'fleet_service_type_default_product_rel',
        'service_type_id',
        'product_id',
        string="Default Products",
        help="Products added automatically to a fleet document when this type is selected.",
    )

    @api.model_create_multi
    def create(self, vals_list):
        # is_license_plate defaults to True; don't let that default collide with an explicit BPKB type.
        for vals in vals_list:
            if vals.get('is_bpkb') and 'is_license_plate' not in vals:
                vals['is_license_plate'] = False
        return super().create(vals_list)

    @api.onchange('is_license_plate')
    def _onchange_is_license_plate(self):
        if self.is_license_plate:
            self.is_bpkb = False

    @api.onchange('is_bpkb')
    def _onchange_is_bpkb(self):
        if self.is_bpkb:
            self.is_license_plate = False

    @api.constrains('is_license_plate', 'is_bpkb')
    def _check_license_plate_bpkb_exclusive(self):
        for rec in self:
            if rec.is_license_plate and rec.is_bpkb:
                raise ValidationError(
                    _("Type '%s' cannot be both 'Is License Plate' and 'Is BPKB'.") % rec.name
                )
