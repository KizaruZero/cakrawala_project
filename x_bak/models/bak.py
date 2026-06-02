from odoo import models, fields, api
from odoo.exceptions import ValidationError


class Bak(models.Model):
    _name = 'bak'
    _description = 'Berita Acara Kejadian'
    _rec_name = 'name'
    # mail.thread → aktifkan chatter & tracking perubahan field
    # mail.activity.mixin → aktifkan fitur Activity di form
    _inherit = ['mail.thread', 'mail.activity.mixin']

    # =====================
    # BASIC
    # =====================
    name = fields.Char(string="BAK Number", readonly=True, default='New')

    partner_id = fields.Many2one('res.partner', string="Nama Client", required=True)
    driver_name = fields.Char(string="Nama Pengemudi", required=True)
    address = fields.Text(string="Alamat Lengkap", required=True)
    phone = fields.Char(string="Nomor Telepon", required=True)

    # =====================
    # STATE
    # =====================
    # Tiga status: draft (baru dibuat), confirm (sudah dikonfirmasi), done (selesai/invoiced)
    state = fields.Selection(
        selection=[
            ('draft', 'Draft'),
            ('confirm', 'Confirmed'),
            ('done', 'Done'),
        ],
        string='Status',
        default='draft',
        copy=False,
        tracking=True,   # Catat perubahan state di chatter (butuh mail.thread)
    )

    # =====================
    # COST
    # =====================
    currency_id = fields.Many2one(
        'res.currency',
        required=True,
        default=lambda self: self.env.company.currency_id
    )
    cost = fields.Monetary(
        string="Biaya Ditanggung Pengemudi / Penyewa / OR",
        currency_field='currency_id',
    )

    # =====================
    # VEHICLE
    # =====================
    vehicle_id = fields.Many2one('fleet.vehicle', string="License Plate", required=True)
    vehicle_model_id = fields.Many2one(
        'fleet.vehicle.model', string="Vehicle",
        related='vehicle_id.model_id', readonly=True,
    )
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
    # INVOICE REFERENCE
    # Many2one ke account.move (Invoice).
    # Field ini diisi otomatis saat action_create_invoice dijalankan.
    # =====================
    invoice_id = fields.Many2one(
        'account.move',
        string='Invoice Reference',
        readonly=True,
        copy=False,
    )

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
    # STATE ACTIONS
    # =====================
    def action_confirm(self):
        """Konfirmasi BAK: state berubah dari draft → confirm."""
        for rec in self:
            if rec.state != 'draft':
                raise ValidationError("Hanya BAK berstatus Draft yang dapat dikonfirmasi.")
            rec.state = 'confirm'

    # =====================
    # CREATE INVOICE
    # Tombol ini hanya visible pada state = confirm (diatur di XML dengan atribut invisible).
    #
    # Logika:
    # 1. Cari produk pertama yang memiliki is_on_risk = True di product.template.
    # 2. Ambil analytic account dari vehicle_id (via x_fleet_document.analytic_account_id
    #    atau field standar fleet).
    # 3. Buat account.move (out_invoice) dengan 1 baris yang sudah di-fill.
    # 4. Simpan referensi invoice di field invoice_id, dan referensi balik di account.move.bak_id.
    # 5. State BAK berubah menjadi done.
    # =====================
    def action_create_invoice(self):
        self.ensure_one()

        if self.state != 'confirm':
            raise ValidationError("Invoice hanya dapat dibuat dari BAK berstatus Confirmed.")

        if self.invoice_id:
            raise ValidationError("Invoice sudah pernah dibuat untuk BAK ini.")

        # 1. Cari produk with is_on_risk = True
        #    Ambil satu produk (should be at most 1 berdasarkan constraint di ProductTemplate)
        on_risk_template = self.env['product.template'].search(
            [('is_on_risk', '=', True)], limit=1
        )
        if not on_risk_template:
            raise ValidationError(
                "Tidak ditemukan produk dengan status 'On Risk'. "
                "Silakan aktifkan satu produk dengan flag 'On Risk' di master data produk."
            )

        # Gunakan product.product (variant) dari template
        product = on_risk_template.product_variant_id

        # 2. Ambil analytic account dari kendaraan
        #    field analytic_account_id ditambahkan oleh modul x_fleet_document
        analytic_distribution = {}
        vehicle = self.vehicle_id
        if vehicle and hasattr(vehicle, 'analytic_account_id') and vehicle.analytic_account_id:
            analytic_distribution = {str(vehicle.analytic_account_id.id): 100.0}

        # 3. Siapkan invoice line values
        invoice_line_vals = {
            'product_id': product.id,
            'name': product.name,
            'quantity': 1,
            'price_unit': self.cost,
        }
        # Tambahkan analytic_distribution hanya jika field tersedia di model account.move.line
        if analytic_distribution and 'analytic_distribution' in self.env['account.move.line']._fields:
            invoice_line_vals['analytic_distribution'] = analytic_distribution

        # 4. Buat customer invoice (out_invoice) dalam status draft
        invoice = self.env['account.move'].create({
            'move_type': 'out_invoice',          # Customer Invoice
            'partner_id': self.partner_id.id,
            'invoice_line_ids': [(0, 0, invoice_line_vals)],
            'bak_id': self.id,                   # Referensi balik ke BAK
        })

        # 5. Simpan referensi di BAK dan ubah state ke done
        self.write({
            'invoice_id': invoice.id,
            'state': 'done',
        })

        # Buka form invoice yang baru dibuat
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'res_id': invoice.id,
            'view_mode': 'form',
            'target': 'current',
        }

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
