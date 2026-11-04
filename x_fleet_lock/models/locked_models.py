from odoo import models


class FleetVehicleLogContract(models.Model):
    _name = 'fleet.vehicle.log.contract'
    _inherit = ['fleet.vehicle.log.contract', 'fleet.lock.mixin']


class FleetVehicleLogServices(models.Model):
    _name = 'fleet.vehicle.log.services'
    _inherit = ['fleet.vehicle.log.services', 'fleet.lock.mixin']


class FleetVehicleOdometer(models.Model):
    _name = 'fleet.vehicle.odometer'
    _inherit = ['fleet.vehicle.odometer', 'fleet.lock.mixin']


class FleetVehicleAssignationLog(models.Model):
    _name = 'fleet.vehicle.assignation.log'
    _inherit = ['fleet.vehicle.assignation.log', 'fleet.lock.mixin']


class FleetVehicleLicensePlateHistory(models.Model):
    _name = 'fleet.vehicle.license.plate.history'
    _inherit = ['fleet.vehicle.license.plate.history', 'fleet.lock.mixin']


class FleetVehicleTyre(models.Model):
    _name = 'fleet.vehicle.tyre'
    _inherit = ['fleet.vehicle.tyre', 'fleet.lock.mixin']


class FleetVehicleTyreHistory(models.Model):
    _name = 'fleet.vehicle.tyre.history'
    _inherit = ['fleet.vehicle.tyre.history', 'fleet.lock.mixin']


class FleetVehicleTyreReference(models.Model):
    _name = 'fleet.vehicle.tyre.reference'
    _inherit = ['fleet.vehicle.tyre.reference', 'fleet.lock.mixin']


class FleetVehicleAki(models.Model):
    _name = 'fleet.vehicle.aki'
    _inherit = ['fleet.vehicle.aki', 'fleet.lock.mixin']


class FleetVehicleAkiHistory(models.Model):
    _name = 'fleet.vehicle.aki.history'
    _inherit = ['fleet.vehicle.aki.history', 'fleet.lock.mixin']


class FleetVehicleAkiReference(models.Model):
    _name = 'fleet.vehicle.aki.reference'
    _inherit = ['fleet.vehicle.aki.reference', 'fleet.lock.mixin']


class FleetVehicleFreeService(models.Model):
    _name = 'fleet.vehicle.free.service'
    _inherit = ['fleet.vehicle.free.service', 'fleet.lock.mixin']


class FleetSpk(models.Model):
    _name = 'fleet.spk'
    _inherit = ['fleet.spk', 'fleet.lock.mixin']


class Bak(models.Model):
    _name = 'bak'
    _inherit = ['bak', 'fleet.lock.mixin']


class BastkManagement(models.Model):
    _name = 'bastk.management'
    _inherit = ['bastk.management', 'fleet.lock.mixin']

    def _fleet_locked_vehicles(self):
        # The handover of a sold unit to its buyer finishes after the unit is Sold. A BASTK
        # not saved yet stays open so its type can be chosen: saving it checks that type.
        return super(BastkManagement, self.filtered(
            lambda bastk: bastk._origin and not bastk.is_disposal
        ))._fleet_locked_vehicles()

    def write(self, vals):
        res = super().write(vals)
        if 'bastk_type_id' in vals:
            self._check_fleet_lock()
        return res


class ReplacementCar(models.Model):
    _name = 'replacement.car'
    _inherit = ['replacement.car', 'fleet.lock.mixin']

    _fleet_lock_fields = ('vehicle_old_id', 'vehicle_new_id')


class ServicePlanning(models.Model):
    _name = 'service.planning'
    _inherit = ['service.planning', 'fleet.lock.mixin']


class DisposalBidding(models.Model):
    _name = 'disposal.bidding'
    _inherit = ['disposal.bidding', 'fleet.lock.mixin']
