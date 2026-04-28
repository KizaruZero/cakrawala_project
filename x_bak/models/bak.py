from odoo import models, fields, api
from odoo.exceptions import ValidationError

class Bak(models.Model):
    _name = 'bak'
    _description = 'Berita Acara Kejadian'
    _rec_name = 'name'

    # =====================
    # BASIC
    # =====================
    name = fields.Char(string="BAK Number", readonly=True, default='New')

    partner_id = fields.Many2one('res.partner', string="Nama Client", required=True)
    driver_name = fields.Char(string="Nama Pengemudi", required=True)
    address = fields.Text(string="Alamat Lengkap", required=True)
    phone = fields.Char(string="Nomor Telepon", required=True)

    # =====================
    # COST
    # =====================
    currency_id = fields.Many2one(
        'res.currency',
        required=True,
        default=lambda self: self.env.company.currency_id
    )
    cost = fields.Monetary(string="Biaya Ditanggung Pengemudi / Penyewa / OR", currency_field='currency_id')

    # =====================
    # VEHICLE
    # =====================
    vehicle_id = fields.Many2one('fleet.vehicle', string="License Plate", required=True)
    vehicle_model_id = fields.Many2one('fleet.vehicle.model', string="Vehicle", related='vehicle_id.model_id', readonly=True)
    year = fields.Selection(string="Year", related='vehicle_id.model_year', readonly=True)
    last_odometer = fields.Float(string="Last Odoometer", required=True)

    # =====================
    # INCIDENT
    # =====================
    ticket_number = fields.Char(string="Ticket Number")

    incident_line_ids = fields.One2many('bak.incident.line', 'bak_id', string="Incident Lines")
    damage_line_ids = fields.One2many('bak.damage.line', 'bak_id', string="Damage Lines")
    
    notes = fields.Html(string="Notes")

    # =====================
    # WORKFLOW
    # =====================
    state = fields.Selection([
        ('draft', 'Draft'),
        ('submitted', 'Submitted'),
        ('done', 'Done')
    ], default='draft')

    # =====================
    # AUTO SEQUENCE
    # =====================
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code('bak.sequence') or 'New'
        return super().create(vals_list)

    # =====================
    # VALIDASI
    # =====================
    @api.constrains('phone')
    def _check_phone(self):
        for rec in self:
            if rec.phone and not rec.phone.isdigit():
                raise ValidationError("Nomor telepon harus angka!")

    # =====================
    # ONCHANGE
    # =====================
    @api.onchange('vehicle_id')
    def _onchange_vehicle(self):
        if self.vehicle_id:
            self.partner_id = self.vehicle_id.driver_id
            if hasattr(self.vehicle_id, 'odometer'):
                self.last_odometer = self.vehicle_id.odometer

    # =====================
    # BUTTON ACTION
    # =====================
    def action_submit(self):
        self.state = 'submitted'

    def action_create_spk(self):
        self.ensure_one()
        action = self.env.ref("x_spk.fleet_spk_action", raise_if_not_found=False)
        if not action:
            return {
                'type': 'ir.actions.act_window',
                'name': 'Create SPK',
                'res_model': 'fleet.spk',
                'view_mode': 'form',
                'target': 'current',
                'context': {
                    'default_vehicle_id': self.vehicle_id.id,
                    'default_bak_id': self.name,
                    'default_customer_id': self.partner_id.id,
                }
            }
        
        result = action.sudo().read()[0]
        form_view = self.env.ref('x_spk.fleet_spk_form', raise_if_not_found=False)
        if form_view:
            result['views'] = [(form_view.id, 'form')]
        result['context'] = {
            'default_vehicle_id': self.vehicle_id.id,
            'default_bak_id': self.name,
            'default_customer_id': self.partner_id.id,
        }
        result['target'] = 'current'
        return result


class BakIncidentLine(models.Model):
    _name = 'bak.incident.line'
    _description = 'BAK Incident Line'

    bak_id = fields.Many2one('bak', string="BAK Reference", required=True, ondelete='cascade')
    incident_date = fields.Datetime(string="Tanggal Kejadian", required=True)
    location = fields.Char(string="Lokasi Kejadian", required=True)
    chronology = fields.Text(string="Detail Kronologi", required=True)


class BakDamageLine(models.Model):
    _name = 'bak.damage.line'
    _description = 'BAK Damage Line'

    bak_id = fields.Many2one('bak', string="BAK Reference", required=True, ondelete='cascade')
    damage = fields.Char(string="Bagian/Komponen yang rusak/hilang", required=True)
    attachment = fields.Binary(string="Attachment")
    attachment_name = fields.Char(string="Attachment Name")
