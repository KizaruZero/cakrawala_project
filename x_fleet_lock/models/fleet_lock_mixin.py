from odoo import _, api, fields, models
from odoo.exceptions import UserError

from odoo.addons.x_bastk_management.models.fleet_vehicle import lock_form_arch


class FleetLockMixin(models.AbstractModel):
    """Read-only records while their vehicle is Sold (sub-status flagged Is Sold).

    Superuser code passes (scheduled actions keep running, disposal BASTK odometer);
    what a user does in the interface does not. Accounting and stock are deliberately
    not locked: the sale of the unit is invoiced and paid after it is Sold.
    """
    _name = 'fleet.lock.mixin'
    _description = 'Fleet Lock'

    _fleet_lock_fields = ('vehicle_id',)

    is_fleet_locked = fields.Boolean(
        string='Read-only (Sold Fleet)',
        compute='_compute_is_fleet_locked',
        compute_sudo=True,
    )

    @api.depends(lambda self: ['%s.is_fleet_locked' % name for name in self._fleet_lock_fields])
    def _compute_is_fleet_locked(self):
        for record in self:
            record.is_fleet_locked = bool(record._fleet_locked_vehicles())

    def _fleet_locked_vehicles(self):
        vehicles = self.env['fleet.vehicle'].sudo()
        for name in self._fleet_lock_fields:
            vehicles |= self.sudo().mapped(name)
        return vehicles.filtered('is_fleet_locked')

    def _check_fleet_lock(self):
        if self.env.su:
            return
        vehicles = self._fleet_locked_vehicles()
        if vehicles:
            raise UserError(_(
                "Fleet %(vehicles)s is Sold: its %(document)s can no longer be created, edited or deleted.",
                vehicles=', '.join(vehicles.mapped('display_name')),
                document=self._description,
            ))

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._check_fleet_lock()
        return records

    def write(self, vals):
        Vehicle = self.env['fleet.vehicle']
        if not all(Vehicle._fleet_lock_free_field(name) for name in vals):
            self._check_fleet_lock()
        res = super().write(vals)
        if any(name in vals for name in self._fleet_lock_fields):
            self._check_fleet_lock()
        return res

    @api.ondelete(at_uninstall=False)
    def _unlink_except_fleet_locked(self):
        self._check_fleet_lock()

    @api.model
    def _get_view(self, view_id=None, view_type='form', **options):
        arch, view = super()._get_view(view_id, view_type, **options)
        if view_type == 'form':
            lock_form_arch(self, arch, _('the fleet of this document is Sold, it can no longer be edited.'))
        return arch, view
