# -*- coding: utf-8 -*-
from odoo import models, fields, api


class AccountAnalyticAccount(models.Model):
    _inherit = 'account.analytic.account'

    asset_number = fields.Char(string="Asset Number")
    license_plate = fields.Char(string="License Plate")
    company_id = fields.Many2one('res.company', string="Company")

    vehicle_id = fields.Many2one(
        'fleet.vehicle',
        string="Fleet Vehicle",
        compute='_compute_fleet_vehicle_info',
        store=True,
        readonly=False,
        ondelete='set null',
        help="Armada kendaraan yang terhubung dengan akun analitik ini.",
    )
    vehicle_product_id = fields.Many2one(
        'product.product',
        string="Model / Type Kendaraan",
        compute='_compute_fleet_vehicle_info',
        store=True,
        readonly=True,
        help="Model / Type produk kendaraan yang diambil dari form Fleet.",
    )
    fleet_state_id = fields.Many2one(
        'fleet.vehicle.state',
        string="Status Fleet",
        compute='_compute_fleet_vehicle_info',
        store=True,
        readonly=True,
        help="Status operasional kendaraan di modul Fleet (Leased, Non-Leased, Inactive, Registered).",
    )

    @api.depends('vehicle_id', 'vehicle_id.state_id', 'vehicle_id.lot_id.product_id', 'license_plate', 'asset_number')
    def _compute_fleet_vehicle_info(self):
        Fleet = self.env['fleet.vehicle'].sudo()
        for account in self:
            vehicle = account.vehicle_id
            if not vehicle:
                if account.id:
                    vehicle = Fleet.search([('analytic_account_id', '=', account.id)], limit=1)
                if not vehicle and account.license_plate:
                    vehicle = Fleet.search([('license_plate', '=', account.license_plate)], limit=1)
                if not vehicle and account.asset_number:
                    vehicle = Fleet.search([('asset_number', '=', account.asset_number)], limit=1)
                if vehicle:
                    account.vehicle_id = vehicle

            if vehicle:
                prod = getattr(vehicle, 'product_id', False)
                if not prod and getattr(vehicle, 'lot_id', False):
                    prod = vehicle.lot_id.product_id
                account.vehicle_product_id = prod
                account.fleet_state_id = vehicle.state_id
                if not vehicle.analytic_account_id and account.id:
                    vehicle.write({'analytic_account_id': account.id})
            else:
                account.vehicle_product_id = False
                account.fleet_state_id = False