from odoo import api, fields, models, _
from odoo.exceptions import UserError


class StockMove(models.Model):
    _inherit = 'stock.move'

    is_replace = fields.Boolean(string='Replace...')

    # Read-only computed dari semua move_line_ids untuk tampilan ringkasan (multi-line)
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

    @api.depends('move_line_ids.initial_license_plate',
                 'move_line_ids.chassis_number',
                 'move_line_ids.engine_number')
    def _compute_vehicle_fields(self):
        for move in self:
            plates = [line.initial_license_plate for line in move.move_line_ids if line.initial_license_plate]
            chassis = [line.chassis_number for line in move.move_line_ids if line.chassis_number]
            engines = [line.engine_number for line in move.move_line_ids if line.engine_number]
            
            move.initial_license_plate = '\n'.join(plates) if plates else False
            move.chassis_number = '\n'.join(chassis) if chassis else False
            move.engine_number = '\n'.join(engines) if engines else False

    # ------------------------------------------------------------------ #
    # Computed: apakah semua unit dalam move ini sudah punya serial number #
    # ------------------------------------------------------------------ #
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
