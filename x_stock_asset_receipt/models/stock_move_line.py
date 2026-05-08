from odoo import api, fields, models, _
from odoo.exceptions import UserError


class StockMoveLine(models.Model):
    _inherit = 'stock.move.line'

    initial_license_plate = fields.Char(string='Initial License Plate')
    chassis_number = fields.Char(string='Chassis Number')
    engine_number = fields.Char(string='Engine Number')

    # Relay: is_vehicle dari product untuk keperluan visibility di view
    is_vehicle = fields.Boolean(
        related='product_id.is_vehicle',
        store=False,
        string='Is Vehicle',
    )

    def action_generate_serial_number_line(self):
        """Generate SN untuk baris move line ini saja."""
        self.ensure_one()

        if self.product_id.tracking != 'serial':
            raise UserError(
                _('Product %s is not tracked by serial number.')
                % self.product_id.display_name
            )

        if self.lot_id:
            raise UserError(
                _('This line already has a Serial Number (%s). '
                  'Delete it first to generate a new one.')
                % self.lot_id.name
            )

        # Buat serial number dari sequence
        sequence = self.env['ir.sequence'].next_by_code('asset.serial.number')
        if not sequence:
            raise UserError(_('Sequence for Asset Serial Number is not defined.'))

        # Buat stock.lot dengan data kendaraan
        lot = self.env['stock.lot'].create({
            'name': sequence,
            'product_id': self.product_id.id,
            'company_id': self.company_id.id,
            'initial_license_plate': self.initial_license_plate or '',
            'chassis_number': self.chassis_number or '',
            'engine_number': self.engine_number or '',
        })

        self.write({
            'lot_id': lot.id,
            'lot_name': lot.name,
            'quantity': 1.0,
        })

        # Return action to keep the "Detailed Operations" popup open
        return self.move_id.action_show_details()

    @api.onchange('initial_license_plate', 'chassis_number', 'engine_number')
    def _onchange_sync_vehicle_fields_to_lot(self):
        """Sync vehicle fields ke stock.lot jika lot sudah ada."""
        if self.lot_id:
            self.lot_id.write({
                'initial_license_plate': self.initial_license_plate or '',
                'chassis_number': self.chassis_number or '',
                'engine_number': self.engine_number or '',
            })

    @api.onchange('lot_id')
    def _onchange_lot_id_load_vehicle_fields(self):
        """Ketika lot dipilih manual, load data kendaraan dari lot ke line."""
        if self.lot_id:
            self.initial_license_plate = self.lot_id.initial_license_plate
            self.chassis_number = self.lot_id.chassis_number
            self.engine_number = self.lot_id.engine_number

    def write(self, vals):
        res = super().write(vals)
        # Saat disimpan, pastikan data kendaraan tersync ke lot
        vehicle_fields = {'initial_license_plate', 'chassis_number', 'engine_number'}
        if vehicle_fields & set(vals.keys()):
            for line in self:
                if line.lot_id:
                    line.lot_id.write({
                        k: vals[k]
                        for k in vehicle_fields & set(vals.keys())
                    })
        return res
