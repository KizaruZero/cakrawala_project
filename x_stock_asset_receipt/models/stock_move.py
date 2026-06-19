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
        string='Initial License Plate',
        compute='_compute_vehicle_fields',
        store=False,
        readonly=True,
        sanitize=False,
    )
    display_chassis_number = fields.Html(
        string='Chassis Number',
        compute='_compute_vehicle_fields',
        store=False,
        readonly=True,
        sanitize=False,
    )
    display_engine_number = fields.Html(
        string='Engine Number',
        compute='_compute_vehicle_fields',
        store=False,
        readonly=True,
        sanitize=False,
    )
    display_vehicle_year = fields.Html(
        string='Tahun',
        compute='_compute_vehicle_fields',
        store=False,
        readonly=True,
        sanitize=False,
    )
    display_vehicle_color = fields.Html(
        string='Warna',
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
                # Use Bootstrap 5 classes to make individual badges and stack them vertically
                badges = [f'<div style="margin-bottom: 2px;"><span class="badge rounded-pill {bg_class}" style="font-size: 0.85em;">{item}</span></div>' for item in items]
                return '<div class="d-flex flex-column align-items-start">' + ''.join(badges) + '</div>'
            
            # HTML Fields for UI
            move.display_license_plate = make_badges(plates, 'text-bg-primary')
            move.display_chassis_number = make_badges(chassis, 'text-bg-primary')
            move.display_engine_number = make_badges(engines, 'text-bg-primary')
            move.display_vehicle_year = make_badges(years, 'text-bg-primary')
            move.display_vehicle_color = make_badges(colors, 'text-bg-primary')

            # Original Text Fields
            move.initial_license_plate = '\n'.join(plates) if plates else False
            move.chassis_number = '\n'.join(chassis) if chassis else False
            move.engine_number = '\n'.join(engines) if engines else False
            move.vehicle_year = '\n'.join(years) if years else False
            move.vehicle_color = '\n'.join(colors) if colors else False

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
