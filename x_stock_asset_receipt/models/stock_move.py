from odoo import api, fields, models, _
from odoo.exceptions import UserError


class StockMove(models.Model):
    _inherit = 'stock.move'

    is_replace = fields.Boolean(string='Replace...')

    initial_license_plate = fields.Text(
        string='Initial License Plate',
        compute='_compute_vehicle_fields',
        store=False,
        readonly=True,
    )
    chassis_number = fields.Text(
        string='Chassis Number',
        compute='_compute_vehicle_fields',
        store=False,
        readonly=True,
    )
    engine_number = fields.Text(
        string='Engine Number',
        compute='_compute_vehicle_fields',
        store=False,
        readonly=True,
    )
    vehicle_year = fields.Text(
        string='Tahun',
        compute='_compute_vehicle_fields',
        store=False,
        readonly=True,
    )
    vehicle_color = fields.Text(
        string='Warna',
        compute='_compute_vehicle_fields',
        store=False,
        readonly=True,
    )

    display_license_plate = fields.Html(
        string='Initial License Plate (Badges)',
        compute='_compute_vehicle_fields',
        store=False,
        readonly=True,
        sanitize=False,
    )
    display_chassis_number = fields.Html(
        string='Chassis Number (Badges)',
        compute='_compute_vehicle_fields',
        store=False,
        readonly=True,
        sanitize=False,
    )
    display_engine_number = fields.Html(
        string='Engine Number (Badges)',
        compute='_compute_vehicle_fields',
        store=False,
        readonly=True,
        sanitize=False,
    )
    display_vehicle_year = fields.Html(
        string='Tahun (Badges)',
        compute='_compute_vehicle_fields',
        store=False,
        readonly=True,
        sanitize=False,
    )
    display_vehicle_color = fields.Html(
        string='Warna (Badges)',
        compute='_compute_vehicle_fields',
        store=False,
        readonly=True,
        sanitize=False,
    )

    @api.depends('move_line_ids.initial_license_plate',
                 'move_line_ids.chassis_number',
                 'move_line_ids.engine_number',
                 'move_line_ids.vehicle_year_id',
                 'move_line_ids.vehicle_color_id')
    def _compute_vehicle_fields(self):
        for move in self:
            plates = [line.initial_license_plate for line in move.move_line_ids if line.initial_license_plate]
            chassis = [line.chassis_number for line in move.move_line_ids if line.chassis_number]
            engines = [line.engine_number for line in move.move_line_ids if line.engine_number]
            years = [line.vehicle_year_id.name for line in move.move_line_ids if line.vehicle_year_id]
            colors = [line.vehicle_color_id.name for line in move.move_line_ids if line.vehicle_color_id]
            
            def make_badges(items, bg_class):
                if not items:
                    return False
                badges = [f'<div style="margin-bottom: 2px;"><span class="badge rounded-pill {bg_class}" style="font-size: 0.85em;">{item}</span></div>' for item in items]
                return '<div class="d-flex flex-column align-items-start">' + ''.join(badges) + '</div>'
            
            move.display_license_plate = make_badges(plates, 'text-bg-primary')
            move.display_chassis_number = make_badges(chassis, 'text-bg-primary')
            move.display_engine_number = make_badges(engines, 'text-bg-primary')
            move.display_vehicle_year = make_badges(years, 'text-bg-primary')
            move.display_vehicle_color = make_badges(colors, 'text-bg-primary')

            move.initial_license_plate = '\n'.join(plates) if plates else False
            move.chassis_number = '\n'.join(chassis) if chassis else False
            move.engine_number = '\n'.join(engines) if engines else False
            move.vehicle_year = '\n'.join(years) if years else False
            move.vehicle_color = '\n'.join(colors) if colors else False

    x_asset_analytic_distribution = fields.Json(
        string='Asset Analytic Distribution',
        copy=False,
        help='Filled from the serial/lot analytic account on stock move lines.',
    )

    analytic_account_domain_ids = fields.Many2many(
        'account.analytic.account',
        string='Allowed Analytic Accounts',
        compute='_compute_analytic_account_domain_ids',
        store=False,
    )

    @api.depends('product_id', 'product_id.is_vehicle')
    def _compute_analytic_account_domain_ids(self):
        """Compute allowed analytic accounts based on the selected vehicle product.
        Used as domain restriction for the analytic_distribution widget in picking views.

        fleet.vehicle.product_id is computed/non-stored, so we cannot filter on it
        directly. Instead: find lots by product_id → get asset_numbers → find vehicles.
        """
        for move in self:
            if move.product_id and move.product_id.is_vehicle:
                lots = self.env['stock.lot'].search([
                    ('product_id', '=', move.product_id.id)
                ])
                asset_numbers = lots.mapped('name')
                if asset_numbers:
                    vehicles = self.env['fleet.vehicle'].search([
                        ('asset_number', 'in', asset_numbers)
                    ])
                    analytic_ids = vehicles.filtered('analytic_account_id').mapped('analytic_account_id').ids
                else:
                    analytic_ids = []
                move.analytic_account_domain_ids = [(6, 0, analytic_ids)]
            else:
                move.analytic_account_domain_ids = [(5, 0, 0)]

    def _get_analytic_distribution(self):
        try:
            res = super()._get_analytic_distribution()
        except AttributeError:
            res = {}
        custom = self.x_asset_analytic_distribution
        if not custom:
            return res if res else {}
        merged = dict(res or {})
        for key, pct in custom.items():
            merged[str(key)] = float(pct)
        return merged

    def _set_asset_analytic_distribution(self, analytic_account):
        self.ensure_one()
        if not analytic_account:
            return
        distribution = {str(analytic_account.id): 100}
        vals = {}
        if self.x_asset_analytic_distribution != distribution:
            vals['x_asset_analytic_distribution'] = distribution
        if 'x_spk_analytic_distribution' in self._fields and self.x_spk_analytic_distribution != distribution:
            vals['x_spk_analytic_distribution'] = distribution
        if not vals:
            return
        if not self.ids:
            self.update(vals)
        else:
            self.write(vals)

    serial_generated = fields.Boolean(
        string='Serial Generated',
        compute='_compute_serial_generated',
        store=False,
    )

    @api.depends('move_line_ids.lot_id', 'lot_ids')
    def _compute_serial_generated(self):
        for move in self:
            move.serial_generated = bool(
                move.move_line_ids.filtered(lambda l: l.lot_id) or move.lot_ids
            )

    @api.constrains('move_line_ids')
    def _check_single_serial_per_asset(self):
        """Pastikan qty tiap move line tidak melebihi 1 untuk produk serial."""
        for move in self:
            if (move.picking_id.picking_type_code == 'incoming'
                    and move.product_id.tracking == 'serial'):
                for line in move.move_line_ids:
                    if line.quantity and line.quantity > 1.0:
                        raise UserError(
                            _('The quantity for serial-tracked assets must be '
                              'exactly 1.0 (product: %s).')
                            % move.product_id.display_name
                        )

    def action_mass_generate_fn(self):
        for move in self:
            if move.product_id.tracking != 'serial':
                continue
            for line in move.move_line_ids:
                if not line.lot_id:
                    sequence = self.env['ir.sequence'].next_by_code('asset.serial.number')
                    if not sequence:
                        raise UserError(_('Sequence for Asset Serial Number is not defined.'))
                    lot = self.env['stock.lot'].create({
                        'name': sequence,
                        'product_id': line.product_id.id,
                        'company_id': line.company_id.id,
                        'initial_license_plate': line.initial_license_plate or '',
                        'chassis_number': line.chassis_number or '',
                        'engine_number': line.engine_number or '',
                        'vehicle_year_id': line.vehicle_year_id.id,
                        'vehicle_color_id': line.vehicle_color_id.id,
                        'analytic_account_id': line.analytic_account_id.id,
                    })
                    line.write({
                        'lot_id': lot.id,
                        'lot_name': lot.name,
                        'quantity': 1.0,
                    })
        return True
