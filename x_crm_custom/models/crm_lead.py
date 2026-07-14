import datetime
from dateutil.relativedelta import relativedelta
from odoo import models, fields, api
from odoo.exceptions import ValidationError, UserError

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
    rpc_document_ids = fields.One2many('rpc.document', 'crm_lead_id', string='RPC Documents')
    rpc_count = fields.Integer(compute='_compute_rpc_count', string='RPC Count')
    has_rpc = fields.Boolean(compute='_compute_has_rpc', string='Has RPC')

    @api.onchange('is_new_customer')
    def _onchange_is_new_customer(self):
        if self.is_new_customer:
            return {
                'warning': {
                    'title': 'Informasi Pembuatan Customer Baru',
                    'message': 'Master Data Customer baru akan dibuat secara otomatis berdasarkan nama dan alamat yang Anda masukkan ketika Lead ini dipindahkan ke tahap (stage) Offering.'
                }
            }

    @api.depends('rpc_document_ids')
    def _compute_rpc_count(self):
        for record in self:
            record.rpc_count = len(record.rpc_document_ids)

    @api.depends('rpc_document_ids')
    def _compute_has_rpc(self):
        for record in self:
            record.has_rpc = bool(record.rpc_document_ids)

    def action_view_rpc_documents(self):
        self.ensure_one()
        action = {
            'name': 'RPC Documents',
            'type': 'ir.actions.act_window',
            'res_model': 'rpc.document',
            'domain': [('crm_lead_id', '=', self.id)],
            'context': {'default_crm_lead_id': self.id},
        }
        if self.rpc_count == 1 and self.rpc_document_ids:
            action['view_mode'] = 'form'
            action['res_id'] = self.rpc_document_ids[0].id
        else:
            action['view_mode'] = 'tree,form'
        return action
    
    client_type_id = fields.Many2one('rpc.parameter', string='Client Type', domain=[('parameter_type', '=', 'type_of_klien')])
    tujuan_id = fields.Many2one('rpc.parameter', string='Tujuan', domain=[('parameter_type', '=', 'tujuan')])
    jenis_transaksi_id = fields.Many2one('rpc.parameter', string='Jenis Transaksi', domain=[('parameter_type', '=', 'jenis_transaksi')])
    custom_source_id = fields.Many2one('rpc.parameter', string='Sumber', domain=[('parameter_type', '=', 'sumber')])
    
    current_population = fields.Integer(string='Current Population')
    existing_fleet = fields.Integer(string='Existing Fleet')

    jenis_kendaraan_id = fields.Many2one('rpc.parameter', string='Jenis Kendaraan', domain=[('parameter_type', '=', 'jenis_kendaraan')])
    sumber_daya_id = fields.Many2one('rpc.parameter', string='Sumber Daya', domain=[('parameter_type', '=', 'sumber_daya')])
    penggunaan_kendaraan_id = fields.Many2one('rpc.parameter', string='Penggunaan Kendaraan', domain=[('parameter_type', '=', 'penggunaan_kendaraan')])
    pemakaian = fields.Many2one('rpc.parameter', string='Pemakaian', domain=[('parameter_type', '=', 'pemakaian')])
    merek_id = fields.Many2one('rpc.parameter', string='Merek', domain=[('parameter_type', '=', 'merek')])
    tahun = fields.Selection(selection='_get_year_selection', string='Tahun')
    state_id = fields.Many2one('rpc.provinsi', string='Provinsi', domain=[])
    city_id = fields.Many2one('rpc.kota', string='Kota', domain="[('provinsi_id', '=', state_id)]")
    
    vehicle_condition = fields.Selection([
        ('used', 'Used Car'),
        ('new', 'Brand New')
    ], string='Used Car/Brand New')
    
    quantity = fields.Integer(string='Quantity')
    tipe_kendaraan = fields.Char(string='Tipe')

    rental_type_id = fields.Many2one('sale.rental.type', string='Rental Type')
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
            stage_id = vals.get('stage_id')
            stage = self.env['crm.stage'].browse(stage_id) if stage_id else self.env['crm.stage'].search([], order='sequence asc, id asc', limit=1)
            if stage and stage.name in ['Offering', 'Negotiation', 'Deal', 'Delivery', 'Cold Leads']:
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
        for record in self:
            stage_id = vals.get('stage_id', record.stage_id.id)
            stage = self.env['crm.stage'].browse(stage_id) if stage_id else record.stage_id
            if stage and stage.name in ['Offering', 'Negotiation', 'Deal', 'Delivery', 'Cold Leads']:
                is_new = vals.get('is_new_customer', record.is_new_customer)
                new_name = vals.get('new_customer_name', record.new_customer_name)
                if is_new and new_name:
                    partner = self.env['res.partner'].create({
                        'name': new_name,
                        'street': vals.get('new_customer_address', record.new_customer_address) or False,
                        'function': vals.get('job_position', record.job_position) or False,
                        'email': vals.get('email_from', record.email_from) or False,
                        'phone': vals.get('phone', record.phone) or False,
                    })
                    vals['partner_id'] = partner.id
                    vals['is_new_customer'] = False
                    vals['new_customer_name'] = False
                    vals['new_customer_address'] = False
                    break

        res = super(CrmLead, self).write(vals)

        # Strict Stage Validation
        if 'stage_id' in vals:
            for record in self:
                stage_name = record.stage_id.name
                missing_fields = []

                # Check New Leads fields if moving to Offering or beyond
                if stage_name in ['Offering', 'Negotiation', 'Deal', 'Delivery', 'Cold Leads']:
                    if not record.client_type_id: missing_fields.append('Client Type')
                    if not record.tujuan_id: missing_fields.append('Tujuan')
                    if not record.jenis_transaksi_id: missing_fields.append('Jenis Transaksi')
                    if not record.custom_source_id: missing_fields.append('Sumber')
                    if not record.partner_id: missing_fields.append('Customer')
                    if not record.user_id: missing_fields.append('Marketing')
                    if not record.contact_name: missing_fields.append('Contact Name')
                    if not record.job_position: missing_fields.append('Job Position')
                    if not record.email_from: missing_fields.append('Email')
                    if not record.phone: missing_fields.append('Phone')

                # Check Offering fields if moving to Negotiation or beyond
                if stage_name in ['Negotiation', 'Deal', 'Delivery', 'Cold Leads']:
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
                if stage_name in ['Deal', 'Delivery', 'Cold Leads']:
                    if not record.sq_number: missing_fields.append('SQ Number')
                    if not record.initial_rpc: missing_fields.append('Initial RPC')
                    if not record.revised_rpc: missing_fields.append('Revised RPC')

                # Check Deal fields if moving to Delivery or beyond
                if stage_name in ['Delivery', 'Cold Leads']:
                    if not record.so_number: missing_fields.append('SO Number')
                    if not record.pr_number: missing_fields.append('PR Number')
                    if not record.po_number: missing_fields.append('PO Number')
                    if not record.contract_number: missing_fields.append('Contract Number')
                    if not record.insurance_clause: missing_fields.append('Insurance Clause')

                # Check Delivery fields if moving to Cold Leads
                if stage_name in ['Cold Leads']:
                    if not record.do_number: missing_fields.append('DO Number')
                    if not record.delivery_category: missing_fields.append('Delivery Category')
                    if not record.bastk_number: missing_fields.append('BASTK')

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

    def action_create_rpc(self):
        for record in self:
            if not record.partner_id:
                raise UserError("Silakan pilih atau buat Customer terlebih dahulu sebelum membuat dokumen RPC.")

            missing_customer_fields = []
            partner = record.partner_id

            # Validate 10 Company Information fields
            company_info_map = [
                ('bidang_usaha', 'Bidang Usaha'),
                ('kepemilikan', 'Kepemilikan'),
                ('pemegang_saham', 'Pemegang Saham'),
                ('group_perusahaan', 'Group Perusahaan'),
                ('ukuran_perusahaan', 'Ukuran Perusahaan'),
                ('catatan_tambahan', 'Deskripsi / Catatan / Informasi Tambahan'),
                ('jumlah_karyawan', 'Jumlah Karyawan'),
                ('jumlah_populasi_fleet', 'Jumlah Populasi Fleet'),
                ('perusahaan_rental_saat_ini', 'Perusahaan Rental saat ini'),
                ('tujuan_pemakaian', 'Tujuan Pemakaian'),
            ]
            for field_name, label in company_info_map:
                if not getattr(partner, field_name, False):
                    missing_customer_fields.append(f"[Company Info] {label}")

            # Validate Legal & Compliance Checklist documents based on is_company
            if partner.is_company:
                company_compliance_map = [
                    ('akte_pendirian_attachment', 'Akte Pendirian & Terakhir Perusahaan'),
                    ('rekening_koran_attachment', 'Rekening Koran 3 Bulan Terakhir'),
                    ('lapkeu_audited_attachment', 'Lapkeu Audited Tahunan Terakhir'),
                    ('ktp_pengurus_attachment', 'KTP/KIMS/Passport Pengurus Perusahaan'),
                    ('domisili_attachment', 'Domisili'),
                    ('nib_attachment', 'NIB'),
                    ('npwp_attachment', 'NPWP'),
                    ('surat_kuasa_attachment', 'Surat Kuasa Penandatanganan'),
                    ('slik_perusahaan_attachment', 'SLIK (Perusahaan)'),
                ]
                for field_name, label in company_compliance_map:
                    if not getattr(partner, field_name, False):
                        missing_customer_fields.append(f"[Legal & Compliance] {label}")
            else:
                individual_compliance_map = [
                    ('ktp_individu_attachment', 'KTP/KIMS/Passport'),
                    ('kartu_keluarga_attachment', 'Kartu Keluarga WNI'),
                    ('sim_attachment', 'SIM yang masih berlaku'),
                    ('referensi_perusahaan_attachment', 'Referensi Perusahaan'),
                    ('surat_permintaan_attachment', 'Surat permintaan sewa/konfirmasi'),
                    ('rekening_3bulan_attachment', 'Rekening 3 bulan terakhir'),
                    ('slik_individu_attachment', 'SLIK (Individu)'),
                    ('dokumen_lainnya_attachment', 'Lainnya'),
                ]
                for field_name, label in individual_compliance_map:
                    if not getattr(partner, field_name, False):
                        missing_customer_fields.append(f"[Legal & Compliance] {label}")

            if missing_customer_fields:
                raise UserError(
                    f"Customer '{partner.name}' masih memiliki data yang belum lengkap pada Master Data Customer (bagian Company Information dan/atau Legal & Compliance Checklist).\n\n"
                    f"Field/Dokumen yang belum lengkap:\n- " + "\n- ".join(missing_customer_fields) + "\n\n"
                    f"Silakan lengkapi data tersebut terlebih dahulu pada profil Customer sebelum membuat RPC."
                )

            provinsi_id = record.state_id.id if record.state_id else False
            kota_id = record.city_id.id if record.city_id else False

            tahun_kendaraan = 0
            if record.tahun and record.tahun.isdigit():
                tahun_kendaraan = int(record.tahun)

            rpc_vals = {
                'partner_id': record.partner_id.id if record.partner_id else False,
                'crm_lead_id': record.id,
                'type_of_klien_id': record.client_type_id.id if record.client_type_id else False,
                'jenis_transaksi_id': record.jenis_transaksi_id.id if record.jenis_transaksi_id else False,
                'tujuan_id': record.tujuan_id.id if record.tujuan_id else False,
                'sumber_id': record.custom_source_id.id if record.custom_source_id else False,
                'sumber_daya_id': record.sumber_daya_id.id if record.sumber_daya_id else False,
                'jenis_kendaraan_id': record.jenis_kendaraan_id.id if record.jenis_kendaraan_id else False,
                'penggunaan_kendaraan_id': record.penggunaan_kendaraan_id.id if record.penggunaan_kendaraan_id else False,
                'pemakaian_id': record.pemakaian.id if record.pemakaian else False,
                'merek_id': record.merek_id.id if record.merek_id else False,

                'type_kendaraan': record.tipe_kendaraan,
                'tahun_kendaraan': tahun_kendaraan,
                'provinsi_id': provinsi_id,
                'kota_id': kota_id,
                'masa_sewa': record.masa_sewa,
                'masa_sewa_buffer': record.masa_sewa_buffer,
                'jumlah_unit': record.quantity or 1,
                'sewa_per_bulan_batas_atas': record.sewa_per_bulan or 0.0,
                'sewa_per_bulan_batas_bawah': record.sewa_per_bulan or 0.0,
                'term_of_payment_hari': 30,
                'term_of_payment_due': 'addb',
            }

            # Avoid missing required field error if something is 0/False
            # The Odoo RPC document creates the document based on defaults and these mapping values.
            new_rpc = self.env['rpc.document'].create(rpc_vals)

            return {
                'name': 'RPC Document',
                'type': 'ir.actions.act_window',
                'res_model': 'rpc.document',
                'res_id': new_rpc.id,
                'view_mode': 'form',
                'target': 'current',
            }

    def action_create_quotation(self):
        self.ensure_one()
        rpc = self.rpc_document_ids[:1]
        if not rpc:
            rpc = self.env['rpc.document'].search([('crm_lead_id', '=', self.id)], order='id desc', limit=1)
        if not rpc:
            raise UserError("Silakan buat dokumen RPC terlebih dahulu sebelum membuat Quotation / Rental Order.")

        sale_rental_type = self.rental_type_id

        merek_name = rpc.merek_id.name if (rpc and rpc.merek_id) else (self.merek_id.name if self.merek_id else '')
        tipe_name = rpc.type_kendaraan if (rpc and rpc.type_kendaraan) else (self.tipe_kendaraan or '')
        if merek_name and tipe_name:
            product_name = f"{merek_name} - {tipe_name}"
        elif merek_name or tipe_name:
            product_name = merek_name or tipe_name
        else:
            product_name = "Rental Kendaraan - Reguler"

        product = self.env['product.product'].search([('name', '=ilike', product_name)], limit=1)
        if not product:
            goods_category = self.env['product.category'].search([('name', '=ilike', 'Goods')], limit=1)
            if not goods_category:
                goods_category = self.env['product.category'].search([], limit=1)

            product = self.env['product.product'].create({
                'name': product_name,
                'type': 'consu',
                'is_storable': True,
                'tracking': 'serial',
                'categ_id': goods_category.id if goods_category else False,
                'sale_ok': True,
                'purchase_ok': True,
                'purchase_method': 'purchase',
                'invoice_policy': 'order',
                'is_vehicle': True,
                'list_price': rpc.sewa_per_bulan_batas_atas if (rpc and rpc.sewa_per_bulan_batas_atas) else (self.sewa_per_bulan or 0.0),
            })

        qty = rpc.jumlah_unit if (rpc and rpc.jumlah_unit) else (self.quantity or 1)
        price_unit = rpc.sewa_per_bulan_batas_atas if (rpc and rpc.sewa_per_bulan_batas_atas) else (self.sewa_per_bulan or 0.0)

        order_line_vals = [(0, 0, {
            'product_id': product.id,
            'name': product_name,
            'product_uom_qty': qty,
            'price_unit': price_unit,
        })]

        masa_sewa_val = rpc.masa_sewa if (rpc and rpc.masa_sewa) else (self.masa_sewa or 1)
        now_dt = fields.Datetime.now()
        return_dt = now_dt + relativedelta(months=masa_sewa_val)

        so_vals = {
            'partner_id': rpc.partner_id.id if (rpc and rpc.partner_id) else (self.partner_id.id if self.partner_id else False),
            'opportunity_id': self.id,
            'attention_up': self.contact_name or '',
            'order_type_id': rpc.jenis_transaksi_id.id if (rpc and rpc.jenis_transaksi_id) else False,
            'rental_type_id': sale_rental_type.id if sale_rental_type else False,
            'location_id': rpc.kota_id.id if (rpc and rpc.kota_id) else (self.city_id.id if self.city_id else False),
            'masa_sewa_bulan': masa_sewa_val,
            'rental_start_date': now_dt,
            'rental_return_date': return_dt,
            'is_rental_order': True,
            'order_line': order_line_vals,
        }

        sale_order = self.env['sale.order'].create(so_vals)

        rental_form_view = self.env.ref('sale_renting.rental_order_primary_form_view', raise_if_not_found=False)

        return {
            'name': 'Rental Order',
            'type': 'ir.actions.act_window',
            'res_model': 'sale.order',
            'res_id': sale_order.id,
            'view_mode': 'form',
            'view_id': rental_form_view.id if rental_form_view else False,
            'context': {
                'in_rental_app': 1,
                'default_is_rental_order': True,
            },
            'target': 'current',
        }

    def _prepare_address_values_from_partner(self, partner):
        res = super()._prepare_address_values_from_partner(partner)
        if partner:
            res['street'] = partner.street or False
            res['street2'] = partner.street2 or False
            res['zip'] = partner.zip or False
        else:
            res['street'] = False
            res['street2'] = False
            res['zip'] = False

        if 'state_id' in res:
            partner_state = partner.state_id if partner and partner.state_id else False
            if partner_state:
                rpc_prov = self.env['rpc.provinsi'].search([('name', '=ilike', partner_state.name)], limit=1)
                res['state_id'] = rpc_prov.id if rpc_prov else False
            else:
                res['state_id'] = False

        if partner and partner.city:
            rpc_kota = self.env['rpc.kota'].search([('name', '=ilike', partner.city)], limit=1)
            if rpc_kota:
                res['city_id'] = rpc_kota.id
            else:
                res['city_id'] = False
        elif not partner:
            res['city_id'] = False

        return res
