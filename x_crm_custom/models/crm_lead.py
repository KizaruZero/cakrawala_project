import datetime
from odoo import models, fields, api

class CrmLead(models.Model):
    _inherit = 'crm.lead'

    def _get_year_selection(self):
        current_year = datetime.datetime.now().year
        return [(str(y), str(y)) for y in range(1990, current_year + 11)]

    is_new_customer = fields.Boolean(string='New Customer?', default=False)
    new_customer_name = fields.Char(string='New Customer Name')
    new_customer_address = fields.Char(string='Address')
    job_position = fields.Char(string='Job Position')
    
    client_type_id = fields.Many2one('crm.client.type', string='Client Type')
    tujuan_id = fields.Many2one('crm.tujuan', string='Tujuan')
    jenis_transaksi_id = fields.Many2one('crm.jenis.transaksi', string='Jenis Transaksi')
    custom_source_id = fields.Many2one('crm.source.custom', string='Source (Custom)')
    
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
