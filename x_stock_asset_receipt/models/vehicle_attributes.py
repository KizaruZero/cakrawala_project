from odoo import api, models, fields


class VehicleAttributeMixin(models.AbstractModel):
    """Master data resolved from the free text Fleet stores.

    Fleet keeps Warna and Tahun as plain values on the vehicle, while the lot
    and the receipt lines point at a master record. Both sides of that bridge
    need the same lookup, so it lives here instead of being written out per
    caller.
    """
    _name = 'vehicle.attribute.mixin'
    _description = 'Vehicle Attribute Master Data'

    name = fields.Char(required=True)
    active = fields.Boolean(default=True)

    @api.model
    def _resolve_by_name(self, name, create_if_missing=True):
        """Master record for ``name``, created when it is not on file yet.

        Matching ignores case and surrounding blanks, because the Fleet side is
        free text — an exact match used to drop values like "2023" whenever the
        master list did not already carry that exact spelling.

        Creating the missing record mirrors what the goods receipt already does
        (``stock.move.line._resolve_vehicle_year``), where the value comes from
        a Fleet record. The Excel import deliberately does the opposite and
        refuses to create master data from a typed cell — there the value is
        user input and a typo must be reported, not stored.
        """
        if not name:
            return self.browse()
        clean_name = str(name).strip()
        if not clean_name:
            return self.browse()
        record = self.search([('name', '=ilike', clean_name)], limit=1)
        if not record and create_if_missing:
            record = self.create({'name': clean_name.capitalize()})
        return record


class VehicleColor(models.Model):
    _name = 'vehicle.color'
    _description = 'Vehicle Color'
    _inherit = ['vehicle.attribute.mixin']

    name = fields.Char(string='Color Name', required=True)
    active = fields.Boolean(default=True)


class VehicleYear(models.Model):
    _name = 'vehicle.year'
    _description = 'Vehicle Year'
    _inherit = ['vehicle.attribute.mixin']

    name = fields.Char(string='Year', required=True)
    active = fields.Boolean(default=True)
