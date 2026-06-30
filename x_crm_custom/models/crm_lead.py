import datetime
from odoo import models, fields, api
from odoo.exceptions import ValidationError

class CrmLead(models.Model):
    _inherit = 'crm.lead'

    def _get_year_selection(self):
        current_year = datetime.datetime.now().year
        return [(str(y), str(y)) for y in range(1990, current_year + 11)]

    is_new_customer = fields.Boolean(string='New Customer?', default=False)
    new_customer_name = fields.Char(string='New Customer Name')
    new_customer_address = fields.Char(string='Address')
    job_position = fields.Char(string='Job Position')
    stage_name = fields.Char(related='stage_id.name', string='Stage Name')
    
    client_type_id = fields.Many2one('crm.client.type', string='Client Type')
    tujuan_id = fields.Many2one('crm.tujuan', string='Tujuan')
    jenis_transaksi_id = fields.Many2one('crm.jenis.transaksi', string='Jenis Transaksi')
    custom_source_id = fields.Many2one('crm.source.custom', string='Source')
    
    current_population = fields.Integer(string='Current Population')
    existing_fleet = fields.Integer(string='Existing Fleet')

    jenis_kendaraan_id = fields.Many2one('crm.jenis.kendaraan', string='Jenis Kendaraan')
    sumber_daya_id = fields.Many2one('crm.sumber.daya', string='Sumber Daya')
    penggunaan_kendaraan_id = fields.Many2one('crm.penggunaan.kendaraan', string='Penggunaan Kendaraan')
    pemakaian = fields.Many2one('crm.pemakaian', string='Pemakaian')
    merek_id = fields.Many2one('fleet.vehicle.model.brand', string='Merek')
    tahun = fields.Selection(selection='_get_year_selection', string='Tahun')
    state_id = fields.Many2one('res.country.state', string='Provinsi')
    city_id = fields.Many2one('res.city', string='Kota')
    
    vehicle_condition = fields.Selection([
        ('used', 'Used Car'),
        ('new', 'Brand New')
    ], string='Used Car/Brand New')
    
    quantity = fields.Integer(string='Quantity')
    tipe_kendaraan = fields.Char(string='Tipe')

    rental_type_id = fields.Many2one('crm.rental.type', string='Rental Type')
    usage_location_id = fields.Many2one('crm.usage.location', string='Usage Location')
    sewa_per_bulan = fields.Float(string='Sewa/Bulan')
    harga_otr = fields.Float(string='Harga OTR')
    masa_sewa = fields.Integer(string='Masa Sewa (Bulan)')
    masa_sewa_buffer = fields.Integer(string='Masa Sewa Buffer (Bulan)')
    
    total_forecast = fields.Float(string='Total Forecast', compute='_compute_total_forecast', store=True)
    estimated_delivery = fields.Date(string='Estimated Delivery')
    offering_notes = fields.Text(string='Notes')

    sq_number = fields.Char(string='Sales Quotation No')
    initial_rpc = fields.Char(string='Initial RPC')
    revised_rpc = fields.Char(string='Revised RPC')

    so_number = fields.Char(string='Sales Order No')
    pr_number = fields.Char(string='PR No')
    po_number = fields.Char(string='PO No')
    contract_number = fields.Char(string='Contract')
    insurance_clause = fields.Char(string='Insurance Clause')

    do_number = fields.Char(string='DO Number')
    delivery_category = fields.Char(string='Delivery Category')
    bastk_number = fields.Char(string='BASTK')

    @api.depends('sewa_per_bulan', 'masa_sewa')
    def _compute_total_forecast(self):
        for record in self:
            record.total_forecast = record.sewa_per_bulan * record.masa_sewa

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('is_new_customer') and vals.get('new_customer_name'):
                partner = self.env['res.partner'].create({
                    'name': vals.get('new_customer_name'),
                    'street': vals.get('new_customer_address') or False,
                    'function': vals.get('job_position') or False,
                    'email': vals.get('email_from') or False,
                    'phone': vals.get('phone') or False,
                })
                vals['partner_id'] = partner.id
                vals['is_new_customer'] = False
                vals['new_customer_name'] = False
                vals['new_customer_address'] = False
        return super(CrmLead, self).create(vals_list)

    def write(self, vals):
        if len(self) == 1:
            is_new = vals.get('is_new_customer', self.is_new_customer)
            new_name = vals.get('new_customer_name', self.new_customer_name)
            new_address = vals.get('new_customer_address', self.new_customer_address)
            
            if is_new and new_name:
                partner = self.env['res.partner'].create({
                    'name': new_name,
                    'street': new_address or False,
                    'function': vals.get('job_position', self.job_position) or False,
                    'email': vals.get('email_from', self.email_from) or False,
                    'phone': vals.get('phone', self.phone) or False,
                })
                vals['partner_id'] = partner.id
                vals['is_new_customer'] = False
                vals['new_customer_name'] = False
                vals['new_customer_address'] = False

        res = super(CrmLead, self).write(vals)

        # Strict Stage Validation
        if 'stage_id' in vals:
            for record in self:
                stage_name = record.stage_id.name
                missing_fields = []
                
                # Check New Leads fields if moving to Offering or beyond
                if stage_name in ['Offering', 'Negotiation', 'Deal', 'Delivery']:
                    if not record.client_type_id: missing_fields.append('Client Type')
                    if not record.tujuan_id: missing_fields.append('Tujuan')
                    if not record.jenis_transaksi_id: missing_fields.append('Jenis Transaksi')
                    if not record.custom_source_id: missing_fields.append('Source')
                    if not record.partner_id: missing_fields.append('Customer')
                    if not record.user_id: missing_fields.append('Marketing')
                    if not record.contact_name: missing_fields.append('Contact Name')
                    if not record.job_position: missing_fields.append('Job Position')
                    if not record.email_from: missing_fields.append('Email')
                    if not record.phone: missing_fields.append('Phone')

                # Check Offering fields if moving to Negotiation or beyond
                if stage_name in ['Negotiation', 'Deal', 'Delivery']:
                    if not record.jenis_kendaraan_id: missing_fields.append('Jenis Kendaraan')
                    if not record.vehicle_condition: missing_fields.append('Vehicle Condition')
                    if not record.quantity: missing_fields.append('Quantity')
                    if not record.sumber_daya_id: missing_fields.append('Sumber Daya')
                    if not record.penggunaan_kendaraan_id: missing_fields.append('Penggunaan Kendaraan')
                    if not record.pemakaian: missing_fields.append('Pemakaian')
                    if not record.merek_id: missing_fields.append('Merek')
                    if not record.tipe_kendaraan: missing_fields.append('Tipe Kendaraan')
                    if not record.tahun: missing_fields.append('Tahun')
                    if not record.state_id: missing_fields.append('State')
                    if not record.city_id: missing_fields.append('City')
                    if not record.sewa_per_bulan: missing_fields.append('Sewa per Bulan')
                    if not record.harga_otr: missing_fields.append('Harga OTR')
                    if not record.rental_type_id: missing_fields.append('Rental Type')
                    if not record.masa_sewa: missing_fields.append('Masa Sewa')
                    if not record.masa_sewa_buffer: missing_fields.append('Masa Sewa Buffer')
                    if not record.usage_location_id: missing_fields.append('Usage Location')
                    if not record.estimated_delivery: missing_fields.append('Estimated Delivery')

                # Check Negotiation fields if moving to Deal or beyond
                if stage_name in ['Deal', 'Delivery']:
                    if not record.sq_number: missing_fields.append('SQ Number')
                    if not record.initial_rpc: missing_fields.append('Initial RPC')
                    if not record.revised_rpc: missing_fields.append('Revised RPC')

                # Check Deal fields if moving to Delivery
                if stage_name in ['Delivery']:
                    if not record.so_number: missing_fields.append('SO Number')
                    if not record.pr_number: missing_fields.append('PR Number')
                    if not record.po_number: missing_fields.append('PO Number')
                    if not record.contract_number: missing_fields.append('Contract Number')
                    if not record.insurance_clause: missing_fields.append('Insurance Clause')

                if missing_fields:
                    raise ValidationError(
                        "Validasi Gagal! Anda tidak dapat memindahkan Lead ini ke stage '%s'.\n"
                        "Harap lengkapi field wajib berikut terlebih dahulu:\n- %s" % (
                            stage_name, '\n- '.join(missing_fields)
                        )
                    )

        return res

    def action_next_stage(self):
        for record in self:
            stages = self.env['crm.stage'].search([], order='sequence asc, id asc')
            stage_ids = stages.ids
            if record.stage_id.id in stage_ids:
                current_idx = stage_ids.index(record.stage_id.id)
                if current_idx < len(stage_ids) - 1:
                    next_stage_id = stage_ids[current_idx + 1]
                    record.write({'stage_id': next_stage_id})
