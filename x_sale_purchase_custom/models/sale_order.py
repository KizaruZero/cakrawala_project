# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError
from dateutil.relativedelta import relativedelta
import calendar
import math
import pytz


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    # --- Existing Custom Fields ---
    active = fields.Boolean(default=True, tracking=True)
    rental_type_id = fields.Many2one('sale.rental.type', string='Rental Type')
    rental_type_id_is_related_pr = fields.Boolean(related='rental_type_id.is_related_pr')
    rental_type_id_is_related_po = fields.Boolean(related='rental_type_id.is_related_po')
    
    attention_up = fields.Char(string='Attention / UP', help='Input name of the PIC for this quotation')
    order_type_id = fields.Many2one('rpc.parameter', string='Order Type', domain=[('parameter_type', '=', 'jenis_transaksi')])
    periodic = fields.Selection([
        ('daily', 'Daily (short term)'),
        ('weekly', 'Weekly (short term)'),
        ('monthly', 'Monthly (long term)'),
        ('yearly', 'Yearly (long term)')
    ], string='Periodic', default='monthly')
    masa_sewa_bulan = fields.Integer(string='Masa Sewa (Bulan)')
    duration = fields.Char(string='Duration', compute='_compute_custom_duration', store=True, readonly=False)
    location_id = fields.Many2one('rpc.kota', string='Location')
    x_total_keseluruhan = fields.Monetary(
        string='Total Keseluruhan',
        compute='_compute_total_keseluruhan',
        store=True,
    )

    @api.depends('amount_total', 'masa_sewa_bulan', 'is_rental_order')
    def _compute_total_keseluruhan(self):
        for order in self:
            if order.is_rental_order:
                order.x_total_keseluruhan = order.amount_total * max(1, order.masa_sewa_bulan or 1)
            else:
                order.x_total_keseluruhan = order.amount_total

    # --- New Invoicing Fields (Monthly Rental Invoicing) ---
    invoicing_cycle_period = fields.Selection([
        ('monthly', 'Monthly'),
        ('per_3_months', 'Per 3 Months'),
        ('per_6_months', 'Per 6 Months'),
        ('yearly', 'Yearly'),
        ('as_duration', 'As duration rental'),
    ], string='Invoicing Cycle Period', default='monthly')

    consolidate_invoice = fields.Selection([
        ('yes', 'Yes'),
        ('no', 'No'),
    ], string='Consolidate Invoice', default='yes')

    invoicing_date_monthly = fields.Selection(
        [(str(i), str(i)) for i in range(1, 32)],
        string='Invoicing Date (Every Month)',
        default='5',
        help='Specify the invoice date requested by the customer (1st - 31st of the month).'
    )
    input_line_ids = fields.One2many(
        'sale.order.input.line', 'order_id',
        string='Input Orders', copy=True
    )

    top_billing = fields.Selection([
        ('didepan', 'Didepan'),
        ('dibelakang', 'Dibelakang'),
    ], string='TOP', default='didepan',
       help='Didepan = billed before service period, Dibelakang = billed after service period.')

    billing_rule = fields.Selection([
        ('full_charge', 'Full Charge'),
        ('prorate', 'Prorate'),
    ], string='Full Charge/Prorate?', default='full_charge')

    invoice_print_lead_time = fields.Integer(
        string='Invoice Print Lead Time (Days Before Cycle Date)',
        default=lambda self: int(self.env['ir.config_parameter'].sudo().get_param(
            'rental_invoicing.default_invoice_lead_time', '12')),
        help='Administrative lead time in days required to prepare invoice before billing date (e.g. H-12 days).'
    )

    estimated_delivery_date_header = fields.Date(
        string='Estimated Delivery Date',
        help='Global estimated delivery date. When set, it auto-populates to all order lines.'
    )

    rental_draft_invoice_count = fields.Integer(
        string='Draft Invoices',
        compute='_compute_rental_invoice_counts',
    )
    rental_confirmed_invoice_count = fields.Integer(
        string='Invoices',
        compute='_compute_rental_invoice_counts',
    )

    # --- Early Termination Fields ---
    is_early_termination_requested = fields.Boolean(
        string='Early Termination Requested', default=False, tracking=True
    )
    et_termination_date = fields.Date(string='Termination Date', tracking=True)
    et_penalty_amount = fields.Float(string='Penalty Amount', digits=(16, 2), tracking=True)
    et_reason = fields.Text(string='Reason for Early Termination', tracking=True)
    et_notes = fields.Text(string='Additional Notes', tracking=True)

    # --- Contracting & Insurance Fields ---
    notify_contract_expiration = fields.Selection([
        ('1_month', '1 Month before'),
        ('2_weeks', '2 Weeks before'),
        ('7_days', '7 Days before'),
    ], string='Notify Contract Expiration', default='1_month', tracking=True)
    contract_content = fields.Html(string='General Template', sanitize=False)
    is_contract_expiration_notified = fields.Boolean(
        string='Contract Expiration Notified', default=False, copy=False
    )

    # --- Existing Computed/Duration ---
    @api.depends('masa_sewa_bulan', 'periodic', 'rental_start_date', 'rental_return_date', 'is_rental_order')
    def _compute_custom_duration(self):
        for order in self:
            if order.is_rental_order and order.rental_start_date and order.rental_return_date:
                days = (order.rental_return_date - order.rental_start_date).days
                if days <= 0 and order.masa_sewa_bulan:
                    days = int(order.masa_sewa_bulan * 30.4167) if order.masa_sewa_bulan != 12 else 365
                order.duration = f"{days} days"
                continue
            if order.is_rental_order and order.masa_sewa_bulan:
                days = int(order.masa_sewa_bulan * 30.4167) if order.masa_sewa_bulan != 12 else 365
                order.duration = f"{days} days"
                continue
            if not order.masa_sewa_bulan:
                if not order.duration:
                    order.duration = ''
                continue
            months = order.masa_sewa_bulan
            if order.periodic == 'daily':
                days = int(months * 30.4167) if months != 12 else 365
                order.duration = f"{days} Days"
            elif order.periodic == 'weekly':
                weeks = int(months * 4) if months != 12 else 48
                order.duration = f"{weeks} Weeks"
            elif order.periodic == 'yearly':
                years = max(1, int(months / 12))
                order.duration = f"{years} Year{'s' if years > 1 else ''}"
            else:
                order.duration = f"{months} Month{'s' if months > 1 else ''}"

    @api.onchange('rental_type_id', 'order_type_id')
    def _onchange_rental_type_periodic(self):
        if self.rental_type_id and 'long' in (self.rental_type_id.name or '').lower():
            self.periodic = 'monthly'
        elif self.order_type_id and 'long' in (self.order_type_id.name or '').lower():
            self.periodic = 'monthly'

    @api.onchange('rental_start_date', 'rental_return_date')
    def _onchange_rental_dates_compute_months(self):
        """Auto-calculate Total Months and Duration (in days) when rental start/return dates are entered."""
        for order in self:
            if order.rental_start_date and order.rental_return_date:
                delta = relativedelta(order.rental_return_date, order.rental_start_date)
                months = delta.years * 12 + delta.months
                if delta.days >= 15:
                    months += 1
                order.masa_sewa_bulan = max(1, months)
                days = (order.rental_return_date - order.rental_start_date).days
                if days > 0:
                    order.duration = f"{days} days"

    # --- Onchange: Estimated Delivery Date propagation ---
    @api.onchange('estimated_delivery_date_header')
    def _onchange_estimated_delivery_date_header(self):
        """When the global estimated delivery date is set, propagate to all order lines."""
        if self.estimated_delivery_date_header:
            for line in self.order_line:
                if not line.display_type:
                    line.estimated_delivery_date = self.estimated_delivery_date_header

    # --- Compute: Rental Invoice Counts ---
    @api.depends('invoice_ids.state', 'invoice_ids.x_is_rental_invoice', 'order_line.invoice_lines.parent_state', 'is_rental_order')
    def _compute_rental_invoice_counts(self):
        for order in self:
            if not order.is_rental_order:
                order.rental_draft_invoice_count = 0
                order.rental_confirmed_invoice_count = 0
                continue
            invoices = order.invoice_ids | order.order_line.invoice_lines.move_id | self.env['account.move'].search([
                ('invoice_origin', '=', order.name),
                ('move_type', 'in', ('out_invoice', 'out_refund')),
            ])
            rental_invs = invoices.filtered(lambda m: m.x_is_rental_invoice or order.is_rental_order)
            order.rental_draft_invoice_count = len(rental_invs.filtered(lambda m: m.state == 'draft'))
            order.rental_confirmed_invoice_count = len(rental_invs.filtered(lambda m: m.state == 'posted'))

    def action_view_rental_draft_invoices(self):
        """Open draft invoices related to this rental order."""
        self.ensure_one()
        invoices = self.invoice_ids | self.order_line.invoice_lines.move_id | self.env['account.move'].search([
            ('invoice_origin', '=', self.name),
            ('move_type', 'in', ('out_invoice', 'out_refund')),
        ])
        draft_invoices = invoices.filtered(lambda m: (m.x_is_rental_invoice or self.is_rental_order) and m.state == 'draft')
        action = self.env['ir.actions.actions']._for_xml_id('account.action_move_out_invoice_type')
        if len(draft_invoices) > 1:
            action['domain'] = [('id', 'in', draft_invoices.ids)]
        elif len(draft_invoices) == 1:
            action['views'] = [(self.env.ref('account.view_move_form').id, 'form')]
            action['res_id'] = draft_invoices.id
        else:
            action['domain'] = [('id', 'in', [])]
        action['context'] = {
            'default_move_type': 'out_invoice',
            'default_x_is_rental_invoice': True,
            'default_invoice_origin': self.name,
        }
        return action

    def action_view_rental_confirmed_invoices(self):
        """Open confirmed/posted invoices related to this rental order."""
        self.ensure_one()
        invoices = self.invoice_ids | self.order_line.invoice_lines.move_id | self.env['account.move'].search([
            ('invoice_origin', '=', self.name),
            ('move_type', 'in', ('out_invoice', 'out_refund')),
        ])
        posted_invoices = invoices.filtered(lambda m: (m.x_is_rental_invoice or self.is_rental_order) and m.state == 'posted')
        action = self.env['ir.actions.actions']._for_xml_id('account.action_move_out_invoice_type')
        if len(posted_invoices) > 1:
            action['domain'] = [('id', 'in', posted_invoices.ids)]
        elif len(posted_invoices) == 1:
            action['views'] = [(self.env.ref('account.view_move_form').id, 'form')]
            action['res_id'] = posted_invoices.id
        else:
            action['domain'] = [('id', 'in', [])]
        action['context'] = {
            'default_move_type': 'out_invoice',
            'default_x_is_rental_invoice': True,
            'default_invoice_origin': self.name,
        }
        return action

    # --- Existing PR/PO relations ---
    pr_related_ids = fields.One2many('employee.purchase.requisition', 'sale_order_id', string='PR Related')
    po_related_ids = fields.One2many('purchase.order', 'sale_order_id', string='PO Related')

    pr_related_html = fields.Html(compute='_compute_pr_po_html', string='PR Related')
    po_related_html = fields.Html(compute='_compute_pr_po_html', string='PO Related')

    @api.depends('pr_related_ids', 'po_related_ids')
    def _compute_pr_po_html(self):
        for order in self:
            pr_links = []
            for pr in order.pr_related_ids:
                url = f"/web#id={pr.id}&model=employee.purchase.requisition&view_type=form"
                pr_links.append(f"<a href='{url}' class='o_form_uri'>{pr.name}</a>")
            order.pr_related_html = "<span>" + ", ".join(pr_links) + "</span>" if pr_links else ""

            po_links = []
            for po in order.po_related_ids:
                url = f"/web#id={po.id}&model=purchase.order&view_type=form"
                po_links.append(f"<a href='{url}' class='o_form_uri'>{po.name}</a>")
            order.po_related_html = "<span>" + ", ".join(po_links) + "</span>" if po_links else ""

    def action_confirm(self):
        if self.env.context.get('x_disposal_skip_rental_type_check'):
            return super(SaleOrder, self).action_confirm()
        for order in self:
            if not order.rental_type_id:
                raise UserError(_("Please select a Rental Type before confirming the order."))
        return super(SaleOrder, self).action_confirm()

    def action_create_pr(self):
        self.ensure_one()
        employee = self.env['hr.employee'].search([('user_id', '=', self.env.uid)], limit=1)
        if not employee:
            raise UserError(_("You must have a linked employee record to create a Purchase Request."))
            
        if not employee.department_id:
            raise UserError(_("The linked employee must have a Department/Division set to create a Purchase Request."))
            
        pr_vals = {
            'sale_order_id': self.id,
            'customer_so_related': self.partner_id.name,
            'rental_type_id': self.rental_type_id.id,
            'employee_id': employee.id,
            'dept_id': employee.department_id.id,
            'department_id': employee.department_id.id,
            'user_id': self.env.uid,
            'internal_reference': self.name,
            'requisition_order_ids': [(0, 0, {
                'product_id': line.product_id.id,
                'description': line.name,
                'quantity': line.product_uom_qty,
                'estimate_price': line.price_unit,
                'uom_id': line.product_uom_id.id,
            }) for line in self.order_line if line.product_id]
        }
        pr = self.env['employee.purchase.requisition'].create(pr_vals)
        
        return {
            'name': _('Purchase Request'),
            'view_mode': 'form',
            'res_model': 'employee.purchase.requisition',
            'res_id': pr.id,
            'type': 'ir.actions.act_window',
            'target': 'current',
        }

    def action_create_po(self):
        self.ensure_one()
        po_vals = {
            'partner_id': self.partner_id.id,
            'sale_order_id': self.id,
            'customer_so_related': self.partner_id.name,
            'rental_type_id': self.rental_type_id.id,
            'order_line': [(0, 0, {
                'product_id': line.product_id.id,
                'name': line.name,
                'product_qty': line.product_uom_qty,
                'product_uom_id': line.product_uom_id.id,
                'price_unit': line.price_unit,
            }) for line in self.order_line if line.product_id]
        }
        po = self.env['purchase.order'].create(po_vals)
        
        return {
            'name': _('Purchase Order'),
            'view_mode': 'form',
            'res_model': 'purchase.order',
            'res_id': po.id,
            'type': 'ir.actions.act_window',
            'target': 'current',
        }

    # ===================================================================
    # CRON: Automated Rental Draft Invoice Generation
    # ===================================================================
    @api.model
    def _cron_generate_rental_draft_invoices(self):
        """Daily cron job to generate draft invoices for rental orders."""
        today = fields.Date.today()
        # Find all confirmed rental orders with invoicing parameters set
        orders = self.search([
            ('state', '=', 'sale'),
            ('is_rental_order', '=', True),
            ('invoicing_cycle_period', '!=', False),
        ])
        for order in orders:
            try:
                order._generate_rental_invoices_if_due(today)
            except Exception:
                # Log error but continue processing other orders
                import logging
                _logger = logging.getLogger(__name__)
                _logger.exception("Error generating rental invoice for SO %s", order.name)

    # ===================================================================
    # CRON: Check Contract Expiration Reminders
    # ===================================================================
    @api.model
    def _cron_check_contract_expiration(self):
        """Daily cron job to check rental contract expiration threshold and alert User PIC."""
        today = fields.Date.today()
        orders = self.search([
            ('is_rental_order', '=', True),
            ('state', 'in', ('sale', 'done')),
            ('notify_contract_expiration', '!=', False),
            ('rental_return_date', '!=', False),
            ('is_contract_expiration_notified', '=', False),
        ])
        from dateutil.relativedelta import relativedelta
        for order in orders:
            threshold_date = False
            if order.notify_contract_expiration == '1_month':
                threshold_date = order.rental_return_date - relativedelta(months=1)
            elif order.notify_contract_expiration == '2_weeks':
                threshold_date = order.rental_return_date - relativedelta(days=14)
            elif order.notify_contract_expiration == '7_days':
                threshold_date = order.rental_return_date - relativedelta(days=7)
            
            if threshold_date:
                if hasattr(threshold_date, 'date'):
                    threshold_date = threshold_date.date()
                if today >= threshold_date:
                    pic_partner = order.user_id.partner_id or self.env.company.partner_id
                    if pic_partner:
                        subject = _("Contract Expiration Reminder: %s") % order.name
                        body = _(
                            "<p>Dear %(pic)s,</p>"
                            "<p>This is an automated reminder that the rental contract for <b>%(order)s</b> (Customer: %(customer)s) "
                            "will expire on <b>%(end_date)s</b>.</p>"
                            "<p>Please initiate timely renewals or returns.</p>"
                        ) % {
                            'pic': pic_partner.name,
                            'order': order.name,
                            'customer': order.partner_id.name,
                            'end_date': order.rental_return_date.strftime('%d-%m-%Y'),
                        }
                        order.message_post(
                            subject=subject,
                            body=body,
                            partner_ids=[pic_partner.id],
                            message_type='notification'
                        )
                        order.is_contract_expiration_notified = True

    def action_request_early_termination(self):
        self.ensure_one()
        self.is_early_termination_requested = True
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Early Termination Requested'),
                'message': _('The Request Early Termination tab is now open. Please complete the required details.'),
                'sticky': False,
                'type': 'info',
                'next': {
                    'type': 'ir.actions.client',
                    'tag': 'reload',
                }
            }
        }

    def action_create_contract(self):
        self.ensure_one()
        customer_name = self.partner_id.name or _("Customer")
        company_name = self.company_id.name or _("PT Cakrawala Rentalindo Sejahtera")
        company_name_full = self.company_id.name or "PT Cakrawala Rentalindo Sejahtera"
        
        # Dynamic Fields with Fallbacks
        customer_address = self.partner_id.contact_address or "[Alamat Customer]"
        customer_phone = self.partner_id.phone or "[Telepon Customer]"
        customer_email = self.partner_id.email or "[Email Customer]"
        customer_pic = self.attention_up or "[Nama Perwakilan]"
        customer_pic_title = "[Jabatan Perwakilan]"
        
        # Hardcoded MY COMPANY Fields (PT Cakrawala Rentalindo Sejahtera)
        company_name_full = "PT Cakrawala Rentalindo Sejahtera"
        company_address = "Rukan The Fifty No.10 Jl. Arteri Kelapa Gading, Pegangsaan Dua Jakarta Utara"
        company_phone = "(021) 29574570"
        company_fax = "(021) 29574571"
        company_pic = "Bumina Elizabeth Tjhin"
        company_pic_title = "Direktur"
        
        today_dt = fields.Date.context_today(self)
        hari_names = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"]
        bulan_names = ["Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli", "Agustus", "September", "Oktober", "November", "Desember"]
        roman_months = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII"]
        
        if today_dt:
            hari_str = hari_names[today_dt.weekday()]
            bulan_str = bulan_names[today_dt.month - 1]
            roman_month = roman_months[today_dt.month - 1]
            tanggal_str = f"{hari_str} tanggal {today_dt.day:02d} {bulan_str} {today_dt.year}"
            year_str = str(today_dt.year)
        else:
            tanggal_str = "-"
            roman_month = "III"
            year_str = "2025"

        short_customer = "".join([word[0] for word in customer_name.split() if word.isalpha() and len(word) > 1]).upper() or "PIHAK KEDUA"
        
        order_code = self.name.split("/")[-1] if self.name and "/" in self.name else (self.name or "0351")
        pks_cakrawala = f"No.{order_code}PS/CRS/{roman_month}/{year_str}"
        pks_partner = f"No. 001A/PKS-LLI/{short_customer}/{roman_month}/{year_str}"

        def art_title(text):
            return f'<div style="font-weight: bold; text-align: justify; margin-top: 16px; margin-bottom: 12px; font-size: 11pt; line-height: 1.25;">{text}</div>'

        def art_p(text, ind=0):
            return f'<div style="text-align: justify; margin-bottom: 12px; font-size: 11pt; line-height: 1.25; margin-left: {ind}px;">{text}</div>'

        def art_item(num, text, ind=0, num_width=24, min_height=0):
            margin_bottom = 12
            col1 = f'<div style="display: table-cell; width: {ind}px;"></div>' if ind > 0 else ''
            return f'<div style="display: table; width: 100%; margin-bottom: {margin_bottom}px; font-size: 11pt; line-height: 1.25;">{col1}<div style="display: table-cell; width: {num_width}px;">{num}</div><div style="display: table-cell; text-align: justify;">{text}</div></div>'

        def art_item_cont(text, ind=0, num_width=24):
            margin_bottom = 12
            col1 = f'<div style="display: table-cell; width: {ind + num_width}px;"></div>'
            return f'<div style="display: table; width: 100%; margin-bottom: {margin_bottom}px; font-size: 11pt; line-height: 1.25;">{col1}<div style="display: table-cell; text-align: justify;">{text}</div></div>'
            


        all_items = []
        pages = []
        
        # ================= PAGE 1 =================
        header_html = f"""
            <div class="contract-header">
                <h4 style="text-align: center; margin-bottom: 2px; font-weight: bold; font-size: 15px;">PERJANJIAN SEWA</h4>
                <div style="text-align: center; margin-top: 2px; margin-bottom: 2px; font-weight: bold; font-size: 15px;">ANTARA</div>
                <h4 style="text-align: center; margin-top: 2px; margin-bottom: 2px; font-weight: bold; font-size: 15px;">{company_name_full.upper()}</h4>
                <div style="text-align: center; margin-top: 2px; margin-bottom: 2px; font-weight: bold; font-size: 15px;">DENGAN</div>
                <h4 style="text-align: center; margin-top: 2px; margin-bottom: 10px; font-weight: bold; font-size: 15px;">{customer_name.upper()}</h4>
                <div style="text-align: center; margin-bottom: 2px; font-weight: bold; font-size: 15px;">{pks_cakrawala}</div>
                <div style="text-align: center; margin-top: 2px; margin-bottom: 15px; font-weight: bold; font-size: 15px;">{pks_partner}</div>
                <div style="border-top: 1px solid #000; margin-bottom: 20px;"></div>
            </div>
        """
        
        intro_html = f"""
            {header_html}
            <div style="margin-bottom: 15px; text-align: justify; font-size: 15px;">
                Perjanjian Sewa ini (selanjutnya disebut 'Perjanjian') dibuat pada hari ini, {tanggal_str} bertempat di Jakarta, oleh dan antara :
            </div>
            {art_item('1.', f'<strong>{company_name_full}</strong>, suatu badan hukum yang didirikan menurut dan berdasarkan hukum negara Republik Indonesia, berkedudukan di {company_address}, bertindak diwakili oleh <strong>{company_pic}</strong> selaku <strong>{company_pic_title}</strong> untuk dan atas nama {company_name_full}, (untuk selanjutnya disebut <strong>\'{company_name.upper()}\'</strong>), dan', 0, 24)}
            {art_item('2.', f'<strong>{customer_name}</strong> suatu badan hukum yang didirikan menurut dan berdasarkan hukum negara Republik Indonesia, berkedudukan di {customer_address}, bertindak diwakili oleh <strong>{customer_pic}</strong> dalam kedudukannya sebagai <strong>{customer_pic_title}</strong> untuk dan atas nama {customer_name} (untuk selanjutnya disebut <strong>\'{short_customer}\'</strong>).', 0, 24)}
            <div style="margin-top: 15px; margin-bottom: 15px; text-align: justify; font-size: 15px;">
                {company_name.upper()} dan {short_customer} selanjutnya disebut sebagai 'PARA PIHAK' dan 'PIHAK'.
            </div>
            <div style="margin-bottom: 10px; font-size: 15px;">Bahwa:</div>
            {art_item('A.', f'{company_name.upper()} menyediakan jasa penyewaan kendaraan kepada para pelanggannya.', 0, 24)}
            {art_item('B.', f'{short_customer} bermaksud untuk menyewa kendaraan tertentu dari {company_name.upper()}.', 0, 24)}
            <div style="margin-top: 15px; margin-bottom: 10px; text-align: justify; font-size: 15px;">
                Dengan ini PARA PIHAK dan PIHAK menyetujui hal-hal sebagai berikut :
            </div>
        """
        
        
        all_items.append(art_title('Pasal 1 – DEFENISI DAN INTERPRETASI'))
        all_items.append(art_item('1.01', 'Kecuali konteksnya mensyaratkan lain, maka beberapa istilah dalam Perjanjian ini akan memiliki arti sebagai berikut :', 0, 32))
        all_items.append(art_item('(a)', 'Hari Kerja adalah setiap hari kecuali hari sabtu, minggu atau hari libur umum di Republik Indonesia. Apabila pada tanggal pelaksanaan kewajiban jatuh pada hari selain Hari Kerja, maka pembayaran tersebut harus dilakukan pada hari kerja sebelumnya.', 20, 24))
        all_items.append(art_item('(b)', f'Tanggal Dimulainya Sewa adalah tanggal saat {short_customer} menandatangani bukti penerimaan barang sewa atas pengiriman kendaraan sesuai dengan', 20, 24))
        
        all_items.append(art_item_cont('data sebagaimana diuraikan dalam Lampiran Perjanjian.', 20, 24))
        all_items.append(art_item('(c)', 'Lampiran adalah Lampiran Perjanjian, segala bentuk kesepakatan, kuasa, pernyataan, Perjanjian dan surat-surat serta formulir-formulir lain yang telah ada maupun yang akan ada.', 20, 24))
        all_items.append(art_item('1.02', 'Interpretasi pada Perjanjian ini adalah sebagai berikut :', 0, 32))
        all_items.append(art_item('(a)', 'Judul dari tiap ketentuan bertujuan dalam memudahkan saja dan tidak mengubah interpretasi dari kalimat pada Perjanjian ini.', 20, 24))
        all_items.append(art_item('(b)', 'Rp berarti mata uang rupiah yang berlaku di Indonesia.', 20, 24))
        
        pages.append(intro_html)
        
        # ================= PAGE 2 =================
        
        all_items.append(art_title('Pasal 2 – JANGKA WAKTU'))
        all_items.append(art_item('1.', f'Perjanjian ini berlaku sejak tanggal .................. sampai dengan tanggal .................. (“Jangka Waktu Perjanjian”) dengan ketentuan {short_customer} berhak sewaktu-waktu melakukan penilaian atau evaluasi Jangka Waktu Perjanjian atas Pekerjaan yang dilakukan TRI.', 0, 24))
        all_items.append(art_item('2.', 'Dalam hal salah satu Pihak berencana untuk memperpanjang jangka waktu Perjanjian maka, Pihak tersebut memberikan informasi pengajuan perpanjangan Perjanjian selambat-lambatnya 30 (tiga puluh) hari sebelum Jangka Waktu Perjanjian berakhir;', 0, 24))
        all_items.append(art_item('3.', 'Apabila perpanjangan jangka waktu disetujui <strong>Para Pihak</strong>, Perjanjian dilakukan secara tertulis dan dituangkan dalam suatu perubahan Perjanjian atau Adenddum yang ditandatangani oleh <strong>Para Pihak</strong>.', 0, 24))
        all_items.append(art_title('PASAL 3 - PEMBERIAN SEWA'))
        all_items.append(art_item('3.01', f'{company_name.upper()} setuju untuk menyewakan (untuk selanjutnya disebut “sewa”), dan {short_customer} menerima sewa atas kendaraan yang data-datanya dijelaskan dalam butir 1 setiap Lampiran Perjanjian, (untuk selanjutnya disebut ‘Kendaraan’) dengan ketentuan dan syarat-syarat di bawah ini.', 0, 32))
        all_items.append(art_item('3.02', 'Jangka waktu sewa kendaraan tersebut menurut perjanjian ini akan di mulai pada tanggal dimulainya sewa (sebagaimana didefinisikan di bawah ini) dan berlaku untuk jangka waktu yang ditentukan dalam butir 2 dari Lampiran Perjanjian ini (untuk selanjutnya disebut ‘Jangka Waktu Sewa’).', 0, 32))
        all_items.append(art_item('3.03', f'{short_customer} mempunyai kewenangan untuk menggunakan kendaraan tersebut di wilayah Republik Indonesia sesuai dengan Undang-Undang Lalu Lintas dan peraturan-peraturan lalu lintas Indonesia.', 0, 32))
        all_items.append(art_title('Pasal 4 - HARGA SEWA'))
        all_items.append(art_item('4.01', 'Besarnya harga sewa (untuk selanjutnya disebut ‘Harga Sewa’) ditentukan dalam butir 3 (b) dari Lampiran Perjanjian ini.', 0, 32))

        all_items.append(art_item('4.02', f'Harga sewa yang dibayar oleh {short_customer} mencakup biaya-biaya dari hal-hal di bawah ini :', 0, 32))
        all_items.append(art_item('(a)', 'Biaya pemeliharaan dan perbaikan.', 20, 24))
        all_items.append(art_item('(b)', 'Kendaraan pengganti.', 20, 24))
        all_items.append(art_item('(c)', 'Biaya perpanjangan Surat Tanda Nomor Kendaraan (STNK).', 20, 24))
        all_items.append(art_item('(d)', 'Asuransi sebagaimana diatur dalam Pasal 9 perjanjian ini.', 20, 24))
        all_items.append(art_item('(e)', 'Biaya derek (towing).', 20, 24))
        all_items.append(art_p(f'Dan tidak termasuk biaya dari hal-hal di bawah ini (tanggung jawab {short_customer}) :'))
        all_items.append(art_item('(a)', 'Bahan bakar, denda, parkir, biaya tol dan perbaikan aksesoris tambahan.', 20, 24))
        all_items.append(art_item('(b)', f'Kerusakan pada kendaraan sebagai akibat dari penggunaan di luar jalur jalan atau kesalahan {short_customer}.', 20, 24))
        all_items.append(art_item('(c)', 'Kerusakan pada kendaraan yang tidak dicakup oleh asuransi kendaraan yang tercantum dalam Pasal 9.01.', 20, 24))
        all_items.append(art_item('4.03', 'Jika ada perubahan atas pajak dan peraturan pemerintah, PARA PIHAK sepakat membicarakan penyesuaian ketentuan-ketentuan dalam perjanjian ini sehubungan dengan perubahan tersebut.', 0, 32))
        all_items.append(art_item('4.04', f'Jika ada kebijaksanaan di bidang moneter oleh pemerintah dan/atau apapun juga yang menyebabkan kenaikan suku bunga atau biaya-biaya lain yang sehubungan dengan harga sewa (selanjutnya disebut ‘kebijaksanaan moneter yang bersifat sementara’), maka {company_name.upper()} akan menyesuaikan harga sewa yang akan diberitahukan secara tertulis oleh {company_name.upper()} kepada {short_customer} dan akan diberlakukan sesuai dengan kesepakatan bersama antara {company_name.upper()} dan {short_customer}.', 0, 32))
        all_items.append(art_title('Pasal 5 – PEMBAYARAN'))
        all_items.append(art_item('5.01', f'Harga sewa akan dibayar oleh {short_customer} sebagai berikut :', 0, 32))
        all_items.append(art_item('(a)', f'Harga sewa pertama akan dibayar oleh {short_customer} pada saat Tanggal Dimulainya Sewa sesuai dengan Pasal 2.02 dan setelah menerima dokumen tagihan dari {company_name.upper()} secara lengkap dan benar dengan tenggang waktu pembayaran 15 (lima belas) hari kerja.', 20, 24))
        
        
        # ================= PAGE 3 =================
        
        all_items.append(art_item('(b)', 'Pembayaran setiap harga sewa selanjutnya akan jatuh pada tanggal yang sama dengan tipe pembayaran seperti yang ditentukan pada butir 3 (a) dari Lampiran Perjanjian ini.', 20, 24))
        all_items.append(art_item('5.02', 'Pembayaran Harga sewa dilakukan pada Hari Kerja.', 0, 32))
        all_items.append(art_item('5.03', f'Sistem pembayaran pertama dilakukan dengan transfer ke rekening atas nama {company_name.upper()} ({company_name_full}).', 0, 32))
        all_items.append(art_item('5.04', f'Sistem Pembayaran kedua sampai dengan akhir Masa Sewa dibayar di muka setiap bulan dilakukan dengan transfer ke rekening atas nama {company_name.upper()} ({company_name_full}) di BCA KCU Pluit dengan Nomor Rekening : 168.565.6789 atau Mandiri KCU Pondok Bambu dengan Nomor Rekening : 1660002988343', 0, 32))
        all_items.append(art_item('5.05', f'Setiap Ketentuan Pajak Pertambahan Nilai (PPN) akan disesuaikan dengan penerapan Undang-undang Perpajakan yang sudah ditetapkan dan diberlakukan nilainya. Adapun nilai pajaknya akan ditambahkan ke harga sewa dan akan menjadi beban {short_customer}, selaku Penyewa dan dibayarkan kepada {company_name.upper()} oleh {short_customer} atas nama PT Mandiri Tunas Finance.', 0, 32))
        all_items.append(art_item('5.06', f'Pajak Penghasilan (PPH Pasal 23) sebesar 2% (dua persen) dari Harga Sewa menjadi beban {company_name.upper()} dan akan dipotong oleh {short_customer} dari harga sewa yang dibayarkan. Selanjutnya pajak penghasilan tersebut disetor dengan surat setoran pajak ke Kas Negara oleh {short_customer} dan {company_name.upper()} berhak menerima Bukti Potong PPH Pasal 23 tersebut.', 0, 32))
        all_items.append(art_title('Pasal 6 - PEMBAYARAN YANG TERTUNDA'))
        all_items.append(art_item('6.01', f'Dalam hal penundaan kewajiban pembayaran dari {short_customer} menurut perjanjian ini termasuk pembayaran Harga Sewa yang ditentukan disini, {short_customer} akan membayar bunga sebesar <i>0.1% (nol koma 1 persen)</i> dari Harga Sewa yang tertunda jika pembayaran lebih dari <i>15 (lima belas) hari kerja</i> sejak tanggal jatuh tempo atau ketentuan pembayaran di lampiran perjanjian ini. Pembayaran untuk setiap hari kalender keterlambatan sampai', 0, 32))
        
        all_items.append(art_item_cont(f'dengan hari diterimanya pembayaran oleh {company_name.upper()}. Jika dalam <i>30 (tiga puluh) hari kerja</i> {short_customer} tidak memenuhi kewajibannya, {company_name.upper()} berhak menarik kendaraan dari {short_customer} dengan pemberitahuan terlebih dahulu kepada {short_customer}, dan {short_customer} dengan Perjanjian ini memberikan kuasa untuk penarikan itu.', 0, 32))
        all_items.append(art_item('6.02', f'{short_customer} menyetujui bahwa {short_customer} tidak akan menuntut atas segala tindakan yang dilakukan oleh {company_name.upper()} sehubungan dengan pasal 5.01. Tindakan yang dimaksud diatas tidak akan dianggap sebagai tindakan pelanggaran {company_name.upper()} dalam hal memasuki tanah milik orang lain atau sebagai pelanggaran terhadap hak-hak {short_customer}.', 0, 32))
        all_items.append(art_title('Pasal 7 - PEMELIHARAAN RUTIN'))
        all_items.append(art_item('7.01', f'{company_name.upper()} akan menunjuk bengkel resmi atau perusahaan manufaktur atau bengkel lain (‘Bengkel Reparasi’). Bengkel Reparasi akan diberi wewenang untuk melakukan pelayanan pemeliharaan rutin untuk kendaraan dan memberikan jadwal pemeliharaan rutin kendaraan bagi {short_customer}.', 0, 32))
        all_items.append(art_item('7.02', f'{short_customer} dapat membawa kendaraan ke Bengkel Reparasi dan meminta agar kendaraan dirawat sesuai dengan jadwal pemeliharaan.', 0, 32))
        all_items.append(art_item('7.03', f'{short_customer} harus memberitahukan {company_name.upper()} sebelum membawa kendaraan ke Bengkel Reparasi untuk menjalani pemeliharaan rutin.', 0, 32))
        all_items.append(art_item('7.04', f'{company_name.upper()} berhak untuk memeriksa kendaraan bersangkutan pada waktu yang diberitahukan oleh Bengkel Reparasi. {company_name.upper()} akan menyediakan pemeliharan dan pelayanan dari Kendaraan seperti yang disarankan oleh Bengkel Reparasi untuk tipe kendaraan tersebut atas biaya {company_name.upper()}.', 0, 32))
        all_items.append(art_title('Pasal 8 - PERBAIKAN KENDARAAN'))
        all_items.append(art_item('8.01', f'Jika kendaraan mengalami kerusakan atau tidak dapat dioperasikan secara normal atau tidak dapat dioperasikan sama sekali, {short_customer} akan memberitahukan Pihak Perta ma, secepatnya untuk memberikan gambaran atas masalah yang timbul dan lokasi Kendaraan tersebut, dan terhadap hal tersebut', 0, 32))

        
        # ================= PAGE 4 =================
        
        all_items.append(art_p(f'{company_name.upper()} menjamin secepatnya dengan usaha semaksimal mungkin akan melakukan hal-hal yang diperlukan agar kendaraan dapat berjalan kembali, termasuk mengusahakan mobil derek untuk menarik kendaraan tersebut ke Bengkel Reparasi.'))
        all_items.append(art_item('8.02', f'Segala perbaikan yang diperlukan bagi kendaraan yang rusak akibat kelalaian {short_customer} mengikuti jadwal pemeliharaan dan atau yang disebabkan oleh kesalahan {short_customer} dalam penggunaan kendaraan yang tidak wajar sesuai dengan hasil pemeriksaan disertai rekomendasi tertulis dari Bengkel Reparasi serta karena pemakaian bahan bakar yang tidak sesuai dengan yang ditentukan oleh pihak manufaktur kendaraan dan setiap perbaikan yang dilakukan tanpa persetujuan {company_name.upper()} menjadi tanggung jawab dan biaya {short_customer}.', 0, 32))
        all_items.append(art_item('8.03', f'{short_customer} harus memberitahukan {company_name.upper()} sebelum membawa kendaraan ke Bengkel Reparasi untuk diperbaiki.', 0, 32))
        all_items.append(art_title('Pasal 9 - KENDARAAN PENGGANTI'))
        all_items.append(art_item('9.01', f'Dalam hal kendaraan tidak dapat digunakan oleh {short_customer} dalam jangka waktu tidak kurang 08 (delapan) jam karena alasan berikut :', 0, 32))
        all_items.append(art_item('(a)', 'Kendaraan dalam pelayanan pemeliharaan rutin yang sesuai dengan jadwal pemeliharaan seperti yang dijelaskan di pasal 6.', 20, 24))
        all_items.append(art_item('(b)', f'Kendaraan dalam perbaikan kecuali yang dijelaskan dalam pasal 7.02 dan dipertimbangkan lain oleh {company_name.upper()}.', 20, 24))
        all_items.append(art_item('(c)', 'Kendaraan rusak dalam kecelakaan.', 20, 24))
        all_items.append(art_p(f'{company_name.upper()} akan menyediakan kendaraan pengganti untuk penggunaan sementara tanpa ada biaya tambahan bagi {short_customer}. Penggunaan kendaraan pengganti harus sesuai dengan ketentuan perjanjian ini. Dalam hal ini kendaraan pengganti adalah dengan tipe kelas yang sama serta dalam kondisi yang baik tetapi tidak diwajibkan dari tahun keluaran yang sama dan {short_customer} akan mengembalikan kendaraan pengganti secepatnya (dalam hari yang sama) apabila kendaraan yang diperbaiki telah selesai.'))
        
        all_items.append(art_item('9.02', f'Dalam hal kecurian, {company_name.upper()} tidak akan menyediakan kendaraan pengganti untuk {short_customer} kecuali ditentukan lain oleh {company_name.upper()}.', 0, 32))
        all_items.append(art_title('Pasal 10 – ASURANSI'))
        all_items.append(art_item('10.01', f'{company_name.upper()} atas biayanya sendiri akan mengasuransikan Kendaraan untuk segala risiko pada perusahaan asuransi yang bereputasi baik. {short_customer} akan membayar risiko sendiri dari setiap klaim asuransi seperti yang ditentukan di butir 4 (a,b,c) dari Lampiran Perjanjian ini. Dan untuk risiko yang tidak dapat diterima oleh perusahaan asuransi, dan/atau terjadinya penolakan klaim asuransi dengan alasan apapun, baik kerugian sebagian maupun kerugian total atau kecurian, maka {short_customer} bersedia menanggung seluruh biaya/kerugian yang timbul, antara lain sebagai berikut :', 0, 32))
        all_items.append(art_item('(a)', f'Kendaraan digunakan oleh pihak lain selain {short_customer} sehingga menyebabkan Kendaraan tersebut hilang, atau', 20, 24))
        all_items.append(art_item('(b)', f'{short_customer} memodifikasi kendaraan termasuk menambah/mengurangi perlengkapan asli kendaraan tanpa persetujuan tertulis dari {company_name.upper()} dan Asuransi, atau', 20, 24))
        all_items.append(art_item('(c)', f'{short_customer} menggunakan kendaraan untuk kompetisi, atau balap atau perlombaan dalam bentuk apapun, atau', 20, 24))
        all_items.append(art_item('(d)', 'Jika terjadi tindak/kasus kriminal yang berhubungan atau menggunakan kendaraan tersebut (pencurian, penyelundupan, penculikan dan atau perbuatan pidana lainnya), atau', 20, 24))
        all_items.append(art_item('(e)', f'Jika penggunaan kendaraan oleh {short_customer} tidak mengikuti perundang-undangan lalu lintas yang berlaku (antara lain : kecelakaan yang disebabkan oleh kecepatan kendaraan yang melebihi peraturan yang ditetapkan, kecelakaan yang terjadi pada saat Kendaraan dikemudikan di bahu jalan bebas hambatan (jalan tol), memasuki/melewati jalan tertutup/terlarang atau tidak diperuntukkan untuk kendaraan', 20, 24))
        
        
        # ================= PAGE 5 =================
        
        all_items.append(art_item_cont('menurut peraturan lalulintas yang berlaku,dll), atau', 20, 24))
        all_items.append(art_item('(f)', 'Pada saat terjadinya kecelakaan, kendaraan dikemudikan oleh seseorang yang tidak memiliki surat izin mengemudi (SIM) yang sah atau oleh seseorang yang berada di bawah pengaruh minuman keras atau sesuatu bahan lain yang memabukkan, atau', 20, 24))
        all_items.append(art_item('(g)', f'{short_customer} mempergunakan kendaraan untuk memuat barang dan atau orang dan atau menarik suatu barang/benda yang mengakibatkan daya beban melebihi kapasitas daya angkut kendaraan, atau dengan cara apapun menjalankan kendaraan secara paksa, atau', 20, 24))
        all_items.append(art_item('(h)', f'{short_customer} mempergunakan kendaraan untuk belajar mengemudi, atau', 20, 24))
        all_items.append(art_item('(i)', 'Barang-barang yang sedang dimuat, ditumpuk, dibongkar, diangkut atau berada di dalam pada Kendaraan pada saat terjadi kecelakaan/kecurian, atau', 20, 24))
        all_items.append(art_item('(j)', 'Kendaraan hilang pada saat valet parking, atau', 20, 24))
        all_items.append(art_item('(k)', 'Pengemudi menerjang banjir dengan sengaja, atau', 20, 24))
        all_items.append(art_item('(l)', f'Tidak ada atau kurangnya Dokumen Pendukung Klaim asuransi yang diajukan {short_customer} kepada {company_name.upper()} seperti yang dijelaskan di pasal 9.02', 20, 24))
        all_items.append(art_item('10.02', f'Dalam hal kecelakaan, termasuk kerusakan/ cedera terhadap pihak ketiga, penumpang atau pengemudi dari kendaraan dan/ atau kehilangan/ kecurian (kerugian total), {short_customer} segera memberitahukan {company_name.upper()} dalam kurun waktu maximal 24 jam (1x24 jam) diikuti dengan penyerahan Dokumen Pendukung Klaim kepada {company_name.upper()}. Adapun Dokumen pendukung klaim tersebut adalah sebagai berikut :', 0, 32))
        all_items.append(art_item('(a)', 'Untuk kendaraan yang hilang dicuri atau kerusakan berat (Total Loss Only) diperlukan :', 20, 24))
        all_items.append(art_item('i.', 'Berita acara kejadian kronologi terjadinya kehilangan atau kecelakaan secara lengkap dan jelas (asli)', 40, 24))
        all_items.append(art_item('ii.', 'Surat keterangan dari Kepolisian setempat (asli)', 40, 24))
        
        all_items.append(art_item('iii.', 'Fotocopy STNK', 40, 24))
        all_items.append(art_item('iv.', 'Fotocopy SIM Pengemudi', 40, 24))
        all_items.append(art_item('v.', 'Dokumen tambahan untuk Kendaraan yang hilang dicuri :', 40, 24))
        all_items.append(art_item('-', 'Surat keterangan kehilangan yang dikeluarkan oleh Kadit Serse Polda Metro setempat a/n Kepala kepolisian Daerah Metro Setempat (asli).', 60, 16))
        all_items.append(art_item('-', 'Surat Tanda Pemblokiran STNK dari Polda Metro Setempat (asli).', 60, 16))
        all_items.append(art_item('(b)', 'Untuk kerusakan sebagian atau kehilangan salah satu perlengkapan yang ada di Kendaraan (partial loss) diperlukan :', 20, 24))
        all_items.append(art_item('i.', 'Berita acara kejadian kronologi terjadinya kehilangan atau kecelakaan secara lengkap dan jelas (asli)', 40, 24))
        all_items.append(art_item('ii.', 'Surat keterangan dari Kepolisian setempat (asli)', 40, 24))
        all_items.append(art_item('iii.', 'Fotocopy STNK dan SIM Pengemudi', 40, 24))
        all_items.append(art_item('(c)', 'Untuk kecelakaan yang mengakibatkan adanya tuntutan dari pihak ketiga diperlukan :', 20, 24))
        all_items.append(art_item('i.', 'Berita acara kejadian kronologi terjadinya kecelakaan secara lengkap dan jelas (asli)', 40, 24))
        all_items.append(art_item('ii.', 'Surat keterangan dari Kepolisian setempat (asli)', 40, 24))
        all_items.append(art_item('iii.', 'Fotocopy STNK (termasuk STNK Pihak ketiga)', 40, 24))
        all_items.append(art_item('iv.', 'Fotocopy SIM Pengemudi (termasuk SIM Pengemudi Kendaraan Pihak Ketiga)', 40, 24))
        all_items.append(art_item('v.', 'Surat Tuntutan dari pihak ketiga (asli)', 40, 24))
        all_items.append(art_p(f'Seluruh biaya pengurusan dokumen pendukung Klaim Asuransi tersebut diatas merupakan beban {short_customer} sendiri.'))
        all_items.append(art_item('10.03', f'Dalam hal terbukti kehilangan kendaraan yang diakibatkan adanya penggelapan, maka {short_customer} wajib membayar ganti rugi kepada {company_name.upper()} atas kendaraan tersebut dengan kendaraan serupa dengan nilai yang sama.', 0, 32))
        all_items.append(art_item('10.04', f'Tanggung jawab pihak ketiga seperti yang ditentukan dibutir 4 (d) dari Lampiran Perjanjian ini akan ditanggung oleh', 0, 32))
        

        # ================= PAGE 6 =================
        
        all_items.append(art_item_cont(f'{company_name.upper()} sesuai dengan syarat-syarat yang diberikan dari perusahaan asuransi yang bersangkutan. {company_name.upper()} akan memberikan santunan atas cacat tetap (tidak berfungsinya bagian organ badan) atau meninggal dunia bagi setiap penumpang dan/ atau pengemudi Kendaraan seperti yang ditentukan di butir 4 (e) dari Lampiran Perjanjian ini. Ketentuan atas santunan ini sesuai dengan syarat-syarat yang diberikan dari perusahaan asuransi yang bersangkutan.', 0, 32))
        all_items.append(art_item('10.05', f'Semua jumlah biaya yang melebihi jumlah yang ditentukan di butir 4 (d,e) dari Lampiran Perjanjian ini akan dibayar oleh {short_customer}. {short_customer} akan bertanggung jawab untuk menyelesaikan perselisihan yang timbul antara {short_customer} dan pihak ketiga dengan biaya {short_customer} sendiri.', 0, 32))
        all_items.append(art_title('Pasal 11- PENGGUNAAN & IZIN KENDARAAN (STNK), MODIFIKASI DAN PENEMPATAN KENDARAAN'))
        all_items.append(art_item('11.01', f'{short_customer} berhak untuk menikmati penggunaan atas kendaraan selama Jangka Waktu Sewa, dan oleh karena itu {company_name.upper()} akan bertanggung jawab untuk menjaga keberlakuan dari STNK kendaraan dan {short_customer} harus memberikan STNK yang diperlukan untuk diperpanjang maximal 2 (dua) minggu sebelum Tanggal STNK berakhir kepada {company_name.upper()}. Semua biaya dan pengeluaran yang diperlukan untuk perpanjangan tersebut menjadi tanggung jawab {company_name.upper()} akan tetapi apabila {short_customer} masih belum memberikan STNK pada saat tanggal STNK berakhir, biaya administrasi keterlambatan yang timbul karenanya dibebankan kepada {short_customer}.', 0, 32))
        all_items.append(art_item('11.02', f'{short_customer} akan bertanggung jawab terhadap kehilangan, kerusakan, kecurian dan/atau kehilangan STNK dari Kendaraan yang disebabkan oleh kelalaian {short_customer} sendiri. Dalam hal tersebut {short_customer} akan membayar semua biaya-biaya yang dikeluarkan untuk pihak kepolisian sehubungan dengan penggantian STNK.', 0, 32))
        all_items.append(art_item('11.03', f'Kendaraan hanya boleh dikemudikan oleh orang yang ditunjuk oleh {short_customer} yang memiliki', 0, 32))

        all_items.append(art_item_cont(f'surat ijin mengemudi (SIM) yang sesuai untuk Kendaraan dan masih berlaku serta wajib mematuhi peraturan lalu lintas yang berlaku. Apabila pengemudi kendaraan harus berurusan dengan Kepolisian atau Aparatnya sehubungan dengan Kendaraan dikemudikan melanggar Peraturan lalulintas, maka segala akibat yang timbul menjadi tanggung jawab dan beban {short_customer}.', 0, 32))
        all_items.append(art_item('11.04', f'{short_customer} tidak akan melakukan modifikasi atau perubahan atas kendaraan seperti mencat kendaraan, menambah aksesoris dan lain-lain tanpa persetujuan tertulis dari {company_name.upper()} terlebih dahulu. {short_customer} akan menanggung biaya-biaya dan pengeluaran-pengeluaran yang timbul atau diisyaratkan sehubungan dengan STNK atau ijin-ijin lainnya yang terkait jika {company_name.upper()} menyetujui perubahan-perubahan tersebut.', 0, 32))
        all_items.append(art_item('11.05', f'Kendaraan harus ditempatkan pada alamat yang disebutkan dalam butir 5 dari Lampiran Perjanjian ini. {short_customer} harus meminta persetujuan tertulis terlebih dahulu dari {company_name.upper()} sebelum memindahkan area pemakaian kendaraan atau tempat penyimpanan Kendaraan.', 0, 32))
        all_items.append(art_title('Pasal 12- PEMBATALAN PERJANJIAN'))
        all_items.append(art_p(f'{short_customer} akan membayar biaya denda pembatalan dari Perjanjian ini kepada {company_name.upper()} dengan alasan apapun juga sebesar <i>25% (dua puluh lima persen)</i> dari Harga Sewa yang belum terbayar berdasarkan jangka waktu Perjanjian, apabila terjadi hal-hal berikut :'))
        all_items.append(art_item('12.01', f'{short_customer} membatalkan Perjanjian ini pada saat {short_customer} telah menandatangani Perjanjian ini dan sebelum saat Tanggal Dimulainya Sewa, atau', 0, 32))
        all_items.append(art_item('12.02', f'{short_customer} membatalkan Perjanjian ini pada saat {company_name.upper()} telah memesan Kendaraan (sesuai dengan Surat Pemesanan Kendaraan) yang telah disepakati dan disetujui oleh {short_customer} yang diperkuat dengan penanda-tanganan Surat Penawaran (proposal), atau', 0, 32))
        all_items.append(art_item('12.03', f'{short_customer} membatalkan Perjanjian ini pada saat {short_customer} menolak untuk menerima Kendaraan karena alasan apapun juga selain', 0, 32))
        

        # ================= PAGE 7 =================
        
        all_items.append(art_item_cont('ketidaksesuaian keadaan kendaraan dengan spesifikasi Kendaraan yang tertera pada Surat Penawaran, atau', 0, 32))
        all_items.append(art_item('12.04', f'{short_customer} membatalkan Perjanjian ini sebelum Masa Sewa berakhir dengan keinginan {short_customer} sendiri dan atau dengan alasan apapun juga termasuk namun tidak terbatas pada terjadinya peristiwa dalam Pasal 3.04, disertai pemberitahuan kepada {company_name.upper()} minimal 5 (lima) hari kerja sebelum Masa Sewa berakhir, dan atau yang dijelaskan dalam Pasal 15 terjadi.', 0, 32))
        all_items.append(art_item('12.05', 'Para Pihak Sepakat untuk menghapus Pasal 1266 dan Pasal 1267 Kitab Undang- Undang Hukum Perdata karena tidak diperlukan lagi izin dari Pengadilan Negeri/ Badan Peradilan lainnya untuk pembatalan perjanjian ini.', 0, 32))
        all_items.append(art_title('Pasal 13 - FORCE MAJEURE'))
        all_items.append(art_item('13.01', 'Dimaksud dengan Force Majeure adalah peristiwa yang terjadi mempengaruhi suatu hal di luar dugaan/kekuasaan PARA PIHAK yang langsung maupun tidak langsung mengenai pelaksanaan perjanjian ini dan atau dapat mengakibatkan tertundanya pemenuhan prestasi dalam perjanjian ini, seperti gempa bumi, banjir, topan, badai/topan, gunung meletus, petir, epidemi, kerusuhan, pemogokan massal, perang, pemberontakan, kebijaksanaan pemerintah dalam bidang moneter/keuangan yang bersifat permanen selain dari kebijaksanaan moneter yang bersifat sementara sebagaimana dimaksud dalam Pasal 3.04.', 0, 32))
        all_items.append(art_item('13.02', 'Semua kerugian dan biaya yang diderita oleh salah satu pihak sebagai akibat terjadinya Force Majeure tersebut bukan merupakan tanggung jawab pihak lain.', 0, 32))
        all_items.append(art_item('13.03', f'Dalam hal terjadi Force Majeure, {short_customer} wajib memberitahukan secara tertulis kepada {company_name.upper()}, selambat-lambatnya dalam waktu 3 (tiga) hari kalender terhitung sejak kejadian dimaksud disertai keterangan dari yang berwenang mengenai peristiwa tersebut.', 0, 32))
        all_items.append(art_item('13.04', f'Apabila dalam jangka waktu sebagaimana dimaksud dalam Pasal 12.03 {short_customer} tidak memberitahukan kejadian Force Majeure', 0, 32))

        all_items.append(art_item_cont(f'tersebut kepada {company_name.upper()}, maka keterlambatan pemenuhan prestasi {short_customer} dianggap bukan sebagai akibat dari Force Majeure.', 0, 32))
        all_items.append(art_item('13.05', f'Dalam pemberitahuan mengenai kejadian Force Majeure dimaksud dalam Pasal 12.03, {short_customer} dapat sekaligus mengajukan permohonan perpanjangan waktu pemenuhan prestasi kepada {company_name.upper()}.', 0, 32))
        all_items.append(art_item('13.06', f'{company_name.upper()} dalam waktu 14 (empat belas) hari kalender terhitung sejak diterimanya permohonan perpanjangan waktu sebagaimana dimaksud dalam Pasal 12.05 akan memberikan jawaban secara tertulis mengenai permohonan dimaksud kepada {short_customer}.', 0, 32))
        all_items.append(art_item('13.07', f'Apabila dalam waktu sebagaimana dimaksud dalam Pasal 12.05, {company_name.upper()} tidak memberikan jawaban terhadap permohonan perpanjangan waktu pemenuhan kewajiban dari {short_customer}, maka {company_name.upper()} dianggap telah memberikan persetujuan terhadap permohonan tersebut.', 0, 32))
        all_items.append(art_title('Pasal 14 - PERNYATAAN DAN JAMINAN'))
        all_items.append(art_p('PARA PIHAK dan PIHAK dengan ini secara tegas menyatakan dan menjamin kepada PARA PIHAK dan PIHAK mengenai kebenaran mereka masing-masing dalam hal-hal sebagai berikut :'))
        all_items.append(art_item('14.01', 'PARA PIHAK dan PIHAK merupakan sebuah badan hukum/badan usaha yang didirikan berdasarkan ketentuan hukum Indonesia, dan telah mendapat pengesahan dari Departemen Hukum dan Hak Asasi Manusia, serta telah melengkapi seluruh ketentuan yang dikehendaki hukum sehubungan dengan status hukum dari PARA PIHAK dan PIHAK tersebut.', 0, 32))
        all_items.append(art_item('14.02', 'PARA PIHAK dan PIHAK berwenang dan berhak untuk menjalankan usaha-usaha yang sekarang dilakukannya dan mempunyai ijin-ijin yang sah untuk menjalankan usahanya tersebut serta dengan ini berjanji untuk memperpanjang atau memperbaharui ijin-ijin tersebut bilamana telah habis masa berlakunya apabila hal-hal sedemikian disyaratkan oleh ketentuan yang berlaku.', 0, 32))
        

        # ================= PAGE 8 =================
        
        all_items.append(art_item('14.03', 'PARA PIHAK dan PIHAK telah memperoleh persetujuan-persetujuan untuk menandatangani perjanjian ini dan dokumen-dokumen lainnya yang terkait.', 0, 32))
        all_items.append(art_item('14.04', 'Penandatanganan perjanjian dan dokumen lainnya sehubungan dengan perjanjian ini tidak akan bertentangan dengan dan/atau melanggar ketentuan-ketentuan perjanjian lain yang telah dilakukan oleh PARA PIHAK dan PIHAK dengan pihak ketiga.', 0, 32))
        all_items.append(art_item('14.05', 'PARA PIHAK dan PIHAK tidak dalam keadaan lalai berdasarkan perjanjian apapun juga dengan pihak ketiga.', 0, 32))
        all_items.append(art_item('14.06', 'PARA PIHAK dan PIHAK tidak mempunyai tunggakan-tunggakan kepada negara termasuk namun tidak terbatas pada tunggakan pajak.', 0, 32))
        all_items.append(art_item('14.07', 'Tidak ada suatu perkara pidana maupun perdata, tuntutan pajak atau sengketa yang sedang berlangsung atau menurut pengetahuan PARA PIHAK dan PIHAK yang mengancam atau yang dapat menimbulkan akibat tidak terbatas terhadap PARA PIHAK dan PIHAK dan/atau harta kekayaan PARA PIHAK dan PIHAK.', 0, 32))
        all_items.append(art_item('14.08', 'Tidak terjadi dan/atau sedang berlangsung suatu keadaan yang akan merupakan persitiwa cidera janji atau yang lewatnya waktu atau dengan adanya pemberitahuan atau kedua-duanya akan merupakan suatu peristiwa cidera janji.', 0, 32))
        all_items.append(art_item('14.09', 'Semua dokumen, data dan surat termasuk fotokopi dan keterangan yang dibuat atau diserahkan oleh PARA PIHAK dan PIHAK adalah telah lengkap, benar dan sah.', 0, 32))
        all_items.append(art_item('14.10', 'PARA PIHAK dan PIHAK akan memberitahukan kepada PARA PIHAK dan PIHAK sesuai dengan jangka waktu yang ditetapkan oleh peraturan perundang-undangan dalam hal terjadinya tindakan sebagai berikut :', 0, 32))
        all_items.append(art_item('(a)', 'Memohon pembubaran, pailit atau penundaan kewajiban pembayaran utang terhadap pihak manapun juga.', 20, 24))
        all_items.append(art_item('(b)', 'Mengubah kegiatan usaha.', 20, 24))
        all_items.append(art_item('(c)', f'Melakukan pembayaran sebelum jatuh tempo pembayaran sehubungan dengan kewajiban {short_customer} kepada {company_name.upper()}.', 20, 24))
        all_items.append(art_item('(d)', 'Mengadakan penyertaan investasi pada perusahaan lain.', 20, 24))

        all_items.append(art_item('(e)', 'Mengadakan merger, akuisisi dan konsolidasi dengan satu atau lebih perusahaan lain.', 20, 24))
        all_items.append(art_item('(f)', f'Mengubah susunan direksi, dewan komisaris dan pemegang saham dalam struktur organisasi {short_customer}.', 20, 24))
        all_items.append(art_title('Pasal 15 – PERISTIWA CIDERA JANJI'))
        all_items.append(art_item('15.01', f'Dengan tidak mengabaikan ketentuan cidera janji dalam peraturan hukum yang berlaku, maka {short_customer} dianggap melakukan cidera janji apabila melakukan beberapa hal sebagai berikut :', 0, 32))
        all_items.append(art_item('(a)', 'Terlambat melakukan kewajibannya sebagaimana diatur dalam Perjanjian ini.', 20, 24))
        all_items.append(art_item('(b)', 'Melakukan tetapi tidak sebagaimana mestinya sebagaimana diatur dalam Perjanjian ini.', 20, 24))
        all_items.append(art_item('(c)', 'Melanggar ketentuan dalam Perjanjian ini baik sebagian maupun keseluruhan.', 20, 24))
        all_items.append(art_item('15.02', f'Dalam hal telah terbukti terjadinya cidera janji oleh {short_customer}, maka {company_name.upper()} berhak untuk melaksanakan satu atau lebih upaya hukum berdasarkan Perjanjian ini dan/atau ketentuan hukum yang berlaku tanpa pemberitahuan atau peringatan sebelumnya kepada {short_customer}, antara lain :', 0, 32))
        all_items.append(art_item('(a)', f'Untuk mengakhiri perjanjian ini dan menyatakan sebagian atau semua uang sewa yang harus dibayar berdasarkan perjanjian ini dan semua biaya lainnya segera jatuh tempo dan wajib dibayar sebagai jumlah yang sudah jatuh tempo atau sebagai jumlah uang yang terutang dan harus dibayar di muka tanpa mengurangi setiap kewajiban lain dari {short_customer} berdasarkan perjanjian ini.', 20, 24))
        all_items.append(art_item('(b)', f'Mengambil kembali Kendaraan atau menuntut pengembaliannya, dengan ketentuan {short_customer} tidak akan dibebaskan dari setiap kewajiban lain berdasarkan perjanjian ini.', 20, 24))
        all_items.append(art_title('Pasal 16 - PENGAKHIRAN PERJANJIAN'))
        all_items.append(art_item('16.01', 'Perjanjian ini akan berakhir dengan sendirinya dengan atau tanpa pemberitahuan terlebih dahulu terhadap terjadinya hal-hal berikut:', 0, 32))
        
        
        # ================= PAGE 9 =================
        
        all_items.append(art_item('(a)', 'Kerugian total atau kecurian Kendaraan, atau', 20, 24))
        all_items.append(art_item('(b)', f'Pembubaran, pengakhiran pailit, kegagalan usaha dari masing-masing pihak atau pernyataan pailit dari {short_customer} atau permulaan dari proses kepailitan atau ketidakmampuan secara hukum yang dialami {short_customer}, atau', 20, 24))
        all_items.append(art_item('(c)', f'{short_customer} menyewakan / memindahtangankan dan atau menjaminkan dalam bentuk apapun dan dengan cara apapun terhadap Kendaraan pada pihak lain serta menggunakan Kendaraan untuk tujuan yang bersifat komersial di luar konteks pekerjaan {short_customer}, tanpa meminta persetujuan tertulis dari {company_name.upper()}, atau', 20, 24))
        all_items.append(art_item('(d)', 'Bila MTF tidak dapat menerima Harga Sewa baru yang ditetapkan sehubungan dengan adanya perubahan Kebijaksanaan pemerintah dibidang moneter dan yang bersifat sementara dan/atau tidak mencapai kesepakatan sebagaimana diatur dalam Pasal 3.04', 20, 24))
        all_items.append(art_item('16.02', f'Apabila hal-hal dalam Pasal 15.01 akan terjadi {short_customer} wajib memberitahukan secara tertulis kepada {company_name.upper()}. Dan pemberitahuan tersebut harus sudah diterima oleh {company_name.upper()} paling lambat 5 (lima) hari kerja sebelum tanggal pengakhiran perjanjian. Selain pengakhiran yang disebutkan dalam 15.01 terjadi, pemberitahuan harus diterima {company_name.upper()} paling lambat 1x24 jam sejak tanggal dan waktu kejadian.', 0, 32))
        all_items.append(art_item('16.03', f'Dalam pengakhiran dari Perjanjian menurut Pasal ini dan/atau pada akhir Masa Sewa, {short_customer} wajib mengembalikan Kendaraan kepada {company_name.upper()} sesuai dengan hari dan tanggal pengakhiran Perjanjian yang tertera dalam surat pemberitahuan tersebut ke lokasi yang ditetapkan oleh {company_name.upper()} dalam keadaan baik seperti pada saat dikirimkan kepada {short_customer}, dengan ketentuan bahwa pemakaian dan akibat-akibatnya yang normal dapat diterima oleh {company_name.upper()}. {short_customer} akan mengganti biaya kepada {company_name.upper()} atas biaya reparasi untuk kerusakan pada Kendaraan yang', 0, 32))

        all_items.append(art_item_cont(f'diakibatkan oleh {short_customer} serta membayar seluruh Pembayaran tertunda dan atau kewajiban-kewajiban {short_customer} yang belum dibayar selama Masa Sewa. Kewajiban pembayaran ini juga berlaku apabila pengakhiran yang disebutkan dalam Pasal 14 terjadi.', 0, 32))
        all_items.append(art_item('16.04', f'Untuk setiap hari kalender keterlambatan pengembalian kendaraan kepada {company_name.upper()} dalam hal-hal menurut Pasal 15.03, {short_customer} menyetujui pembayaran denda sebesar 5% (lima persen) dari Harga sewa.', 0, 32))
        all_items.append(art_title('Pasal 17 - PERUBAHAN'))
        all_items.append(art_p('Semua perubahan terhadap Perjanjian ini akan diadakan dalam bentuk tertulis dan ditandatangani oleh PARA PIHAK dan PIHAK. PARA PIHAK dan PIHAK menyetujui bahwa Perjanjian ini, bersama dengan setiap perubahannya yang mungkin akan dilaksanakan merupakan dan akan merupakan Perjanjian yang menyeluruh, mutlak, sempurna, dan seutuhnya antara PARA PIHAK dan PIHAK.'))
        all_items.append(art_title('Pasal 18 - PILIHAN HUKUM DAN DOMISILI YANG BERLAKU'))
        all_items.append(art_item('18.01', 'Perjanjian ini akan diatur oleh dan ditafsirkan berdasarkan hukum di negara Republik Indonesia.', 0, 32))
        all_items.append(art_item('18.02', f'Sebagai pelaksana dari perjanjian ini, akibat-akibat dan untuk kepastian dari semua perselisihan yang timbul berdasarkan Perjanjian ini apabila terjadi di negara Republik Indonesia, {short_customer} dengan ini memilih domisili yang umum dan tetap pada kantor Badan Arbitrase Nasional Indonesia. Tanpa membatasi ketentuan di atas, {short_customer} setuju bahwa {company_name.upper()} atas pilihannya sendiri mengajukan tiap perselisihan yang timbul sehubungan dengan Perjanjian pada pengadilan lain yang memiliki jurisdiksi atas {company_name.upper()} maupun harta kekayaannya.', 0, 32))
        all_items.append(art_title('Pasal 19 – PENGALIHAN'))
        

        # ================= PAGE 10 =================
        
        address_cakrawala = f"""
        <div style="width: 100%; font-size: 15px; margin-bottom: 15px; margin-top: 15px;">
            <div>Kepada {company_name.upper()} :</div>
            <div>{company_name_full}</div>
            <div>{company_address}</div>
            <div style="display: table; width: 100%;">
                <div style="display: table-row;">
                    <div style="display: table-cell; width: 115px;">Telepon</div>
                    <div style="display: table-cell; width: 15px;">:</div>
                    <div style="display: table-cell;">{company_phone}</div>
                </div>
                <div style="display: table-row;">
                    <div style="display: table-cell;">Faksimil</div>
                    <div style="display: table-cell;">:</div>
                    <div style="display: table-cell;">{company_fax}</div>
                </div>
                <div style="display: table-row;">
                    <div style="display: table-cell;">Untuk perhatian</div>
                    <div style="display: table-cell;">:</div>
                    <div style="display: table-cell;">{company_pic}</div>
                </div>
            </div>
        </div>
        """
        address_mtf = f"""
        <div style="width: 100%; font-size: 15px; margin-bottom: 6px;">
            <div>Kepada {short_customer} :</div>
            <div>{customer_name}</div>
            <div>{customer_address}</div>
            <div style="display: table; width: 100%;">
                <div style="display: table-row;">
                    <div style="display: table-cell; width: 115px;">Telepon</div>
                    <div style="display: table-cell; width: 15px;">:</div>
                    <div style="display: table-cell;">{customer_phone}</div>
                </div>
                <div style="display: table-row;">
                    <div style="display: table-cell;">Email</div>
                    <div style="display: table-cell;">:</div>
                    <div style="display: table-cell;">{customer_email}</div>
                </div>
                <div style="display: table-row;">
                    <div style="display: table-cell;">Untuk perhatian</div>
                    <div style="display: table-cell;">:</div>
                    <div style="display: table-cell;">{customer_pic}</div>
                </div>
            </div>
        </div>
        """
        
        all_items.append(art_item('19.01', f'Baik perjanjian ini, maupun setiap hak dan kewajiban berdasarkan Perjanjian ini tidak dapat dialihkan, baik secara langsung maupun tidak langsung oleh {short_customer} tanpa persetujuan tertulis terlebih dahulu dari {company_name.upper()}.', 0, 32))
        all_items.append(art_item('19.02', f'Perjanjian ini, maupun setiap hak dan kewajiban berdasarkan Perjanjian ini tidak dapat dialihkan, oleh {company_name.upper()} tanpa persetujuan dan/atau pemberitahuan terlebih dahulu kepada {short_customer}.', 0, 32))
        all_items.append(art_title('Pasal 20 - PEMBERITAHUAN'))
        all_items.append(art_item('20.01', 'Setiap koresponden dalam Perjanjian ini dilakukan dalam bahasa Indonesia; dan', 0, 32))
        all_items.append(art_item('(a)', 'Secara tertulis dan diantar langsung secara pribadi atau dengan kilat khusus tercatat atau kurir atau faksimili;', 20, 24))
        all_items.append(art_item('(b)', 'Dianggap telah diterima, kecuali bila diatur lain dalam Perjanjian ini, dalam hal pengiriman dengan f/aksimili pada saat penerimaan nomor-nomor alamat dan kode jawaban atau dalam hal surat yang diantar secara pribadi pada saat diantarkan atau 3 (tiga) hari setelah pengiriman jika dikirim melalui surat tercatat atau pelayanan kurir dikirim.', 20, 24))
        all_items.append(address_cakrawala)
        all_items.append(address_mtf)
        
        all_items.append(art_item('20.02', 'PARA PIHAK dan PIHAK akan saling memberitahukan dengan segera jika ada perubahan alamat dalam Pasal 19.01.', 0, 32))
        
        all_items.append(art_title('Pasal 21- KERAHASIAAN DAN PELINDUNGAN DATA PRIBADI'))
        all_items.append('<div style="margin-top: 12px; margin-bottom: 6px; font-weight: bold; font-size: 15px;">KERAHASIAAN :</div>')
        all_items.append(art_item('1.', f'Informasi Rahasia yang diterima oleh {company_name.upper()} dari {short_customer} wajib dijaga keamanan dan kerahasiaannya, dan {company_name.upper()} dilarang untuk menyampaikan sebagian maupun keseluruhan data, informasi, berkas, surat, maupun dokumen apapun kepada pihak ketiga manapun, tanpa persetujuan secara tertulis dari {short_customer}.', 0, 24))
        all_items.append(art_item('2.', f'{company_name.upper()} menjamin dan bertanggung jawab atas segala kerugian yang timbul akibat tidak terpenuhinya ketentuan ayat 1 Pasal ini yang disebabkan oleh {company_name.upper()}, termasuk setiap karyawan, non karyawan, maupun pihak lainnya yang bekerja sama dengan {company_name.upper()}. Apabila hal demikian terjadi, {company_name.upper()} membebaskan {short_customer} dan bertanggung jawab sepenuhnya atas segala gugatan/tuntutan, termasuk mengganti denda yang dibebankan kepada {short_customer}.', 0, 24))
        all_items.append(art_item('3.', f'{company_name.upper()} dilarang untuk mengungkapkan Informasi Rahasia kepada pihak manapun, kecuali:', 0, 24))
        all_items.append(art_item('a.', f'Direksi, manajemen, karyawan, konsultan, maupun subkontraktor dari {company_name.upper()}; dan/atau', 24, 24))
        all_items.append(art_item('b.', 'Lembaga/otoritas/badan/instansi pemerintah maupun aparat penegak hukum yang berwenang sesuai ketentuan peraturan perundang-undangan yang berlaku.', 24, 24))
        all_items.append(art_item('4.', 'Ketentuan tentang kerahasiaan ini tidak berlaku apabila :', 0, 24))
        all_items.append(art_item('a.', 'Informasi Rahasia yang telah diketahui umum;', 24, 24))
        all_items.append(art_item('b.', 'Informasi Rahasia yang telah diketahui dan dapat dibuktikan oleh', 24, 24))


        # ================= PAGE 11 =================
        
        all_items.append(art_item_cont(f'{company_name.upper()} sebelum Perjanjian ini dibuat dan ditandatangani; dan/atau', 48, 0))
        all_items.append(art_item('c.', 'Informasi Rahasia yang dibuka karena diperintahkan untuk dibuka guna memenuhi perintah Pengadilan atau Instansi atau Otoritas yang berwenang berdasarkan ketentuan hukum yang berlaku.', 24, 24))
        all_items.append(art_item('5.', 'Ketentuan dari pasal kerahasiaan ini tetap berlaku seterusnya meskipun Perjanjian ini berakhir.', 0, 24))
        all_items.append('<div style="margin-top: 24px; margin-bottom: 6px; font-weight: bold; font-size: 15px;">PELINDUNGAN DATA PRIBADI :</div>')
        all_items.append(art_item('1.', 'Para Pihak setuju dan sepakat bahwa penggunaan Data Pribadi yang diungkapkan oleh Pengendali Data kepada Prosesor Data hanya ditujukan semata-mata untuk melaksanakan tujuan sebagaimana diatur dalam Perjanjian. Setiap Pemrosesan Data Pribadi milik Subjek Data wajib dilakukan sesuai kebijakan privasi Pengendali Data, maupun peraturan perundang-undangan yang berlaku terkait dengan pelindungan data pribadi, termasuk setiap peraturan turunannya.', 0, 24))
        all_items.append(art_item('2.', 'Para Pihak setuju dan sepakat bahwa dasar Pemrosesan Data Pribadi adalah persetujuan dari Subjek Data kepada Pengendali Data guna melaksanakan tujuan sesuai diatur dalam Perjanjian.', 0, 24))
        all_items.append(art_item('3.', 'Pengendali Data merupakan satu-satunya Pihak yang berhak untuk menentukan ruang lingkup, mekanisme, tujuan, dan cara Data Pribadi tersebut diproses. Apabila terdapat perubahan mengenai mekanisme dan cara Pemrosesan Data Pribadi tersebut, maka Para Pihak akan menyepakati secara tertulis atas perubahan tersebut .', 0, 24))
        all_items.append(art_item('4.', 'Pengendali Data memastikan telah memiliki persetujuan dari Subjek Data guna melakukan Pemrosesan Data Pribadi yang dilakukan oleh Prosesor Data, yang mana persetujuan dari Subjek Data tersebut hanya sebatas dan', 0, 24))

        all_items.append(art_item_cont('sepanjang untuk melaksanakan tujuan penggunaan yang diatur dalam Perjanjian.', 24, 0))
        all_items.append(art_item('5.', 'Terkait dengan Pemrosesan Data Pribadi tersebut di atas, Prosesor Data menjamin dan bertanggung jawab untuk:', 0, 24))
        all_items.append(art_item('a.', 'Segala perbuatan dan/atau tindakan maupun aktivitas Pemrosesan Data Pribadi yang dilakukan oleh managemen, karyawan, konsultan, subkontraktor, maupun pihak afiliasi dari Pemroses Data yang melakukan aktivitas Pemrosesan Data Pribadi milik Subjek Data sesuai tujuan penggunaan yang diatur dalam Perjanjian, kebijakan privasi Pengendali Data, maupun peraturan perundang-undangan yang berlaku;', 24, 24))
        all_items.append(art_item('b.', 'Menjaga keamanan dan kerahasiaan Data Pribadi serta membatasi pengungkapan Data Pribadi tersebut hanya kepada pihak-pihak yang berkepentingan;', 24, 24))
        all_items.append(art_item('c.', 'Melakukan Pemrosesan Data Pribadi sesuai diatur dalam Perjanjian, kebijakan privasi Pengendali Data dan ketentuan peraturan perundang-undangan terkait pelindungan data pribadi yang berlaku;', 24, 24))
        all_items.append(art_item('d.', 'Memastikan akurasi, kelengkapan, dan konsistensi Pemrosesan Data Pribadi;', 24, 24))
        all_items.append(art_item('e.', 'Memfasilitasi hak Subjek Data sesuai ketentuan peraturan perundang-undangan yang berlaku;', 24, 24))
        all_items.append(art_item('f.', 'Melakukan pengawasan terhadap setiap pihak di bawah kendali Pemroses Data yang terlibat dalam Pemrosesan Data Pribadi, termasuk memastikan pihak-pihak yang terlibat dalam Pemrosesan Data Pribadi memiliki bentuk pelindungan Data Pribadi yang', 24, 24))


        # ================= PAGE 12 =================
        
        all_items.append(art_item_cont('minimal sama dengan Perjanjian ini; dan', 48, 0))
        all_items.append(art_item('g.', 'Hanya melakukan Pemrosesan Data Pribadi sejauh dan sebatas yang diperlukan dalam melaksanakan tujuan penggunaan yang diatur dalam Perjanjian.', 24, 24))
        all_items.append(art_item('6.', 'Prosesor Data dilarang mengungkapkan Data Pribadi kepada pihak manapun dengan alaan maupun tujuan apapun, kecuali pihak-pihak yang terlibat dalam Pemrosesan Data Pribadi sesuai yang tercantum di bawah ini:', 0, 24))
        all_items.append(art_item('a.', 'Direksi, manajemen, karyawan, dan staff yang terlibat hanya sebatas dan sepanjang diperlukan atau dibutuhkan dalam Pemrosesan Data Pribadi;', 24, 24))
        all_items.append(art_item('b.', 'Subkontraktor, maupun konsultan sepanjang pengungkapan Data Pribadi tersebut telah disetujui secara tertulis oleh Pengendali Data. Hal tersebut dapat dilakukan dengan ketentuan Prosesor Data wajib memiliki perjanjian atau dokumen sejenisnya secara tertulis dengan subkontraktor yang mengatur terkait dengan perlindungan Data Pribadi dengan tingkat keamanan yang lebih atau sama dengan yang diatur dalam Perjanjian; dan/atau', 24, 24))
        all_items.append(art_item('c.', 'Lembaga/otoritas/badan/instansi pemerintah maupun aparat penegak hukum yang berwenang sepanjang pengungkapan Data Pribadi tersebut dilakukan untuk melaksanakan peraturan perundang-undangan yang berlaku.', 24, 24))
        all_items.append(art_item('7.', 'Selama jangka waktu Perjanjian, Prosesor Data wajib memberikan kepada Pengendali Data, termasuk namun tidak terbatas pada:', 0, 24))

        all_items.append(art_item('a.', 'Laporan secara tertulis kepada Pengendali Data terperinci terkait dengan cara dan mekanisme yang digunakan dalam Pemrosesan Data Pribadi;', 24, 24))
        all_items.append(art_item('b.', 'Perekaman aktivitas Pemrosesan Data Pribadi sesuai peraturan perundang-undangan yang berlaku; dan/atau', 24, 24))
        all_items.append(art_item('c.', 'Dokumen, informasi, maupun laporan lainnya yang diperlukan oleh Pengendali Data yang terkait dengan Pemrosesan Data Pribadi.', 24, 24))
        all_items.append(art_item_cont('Ketentuan sebagaimana dijelaskan di atas wajib berlaku pula bagi pihak lainnya yang ditunjuk oleh Prosesor Data yang melakukan Pemrosesan Data Pribadi.', 24, 0))
        all_items.append(art_item('8.', 'Dalam hal diperlukan pengalihan atas aktivitas oleh Prosesor Data kepada pihak ketiga yang ditunjuk oleh Prosesor Data, maka Prosesor Data wajib meminta persetujuan secara tertulis terlebih dahulu dari Pengendali Data terkait pengalihan tersebut. Apabila pengalihan tersebut disetujui oleh Pengendali Data, Prosesor Data menjamin dan bertanggung jawab penuh atas Pemrosesan Data Pribadi yang dilakukan oleh pihak ketiga yang ditunjuk oleh Prosesor Data terhadap pelanggaran, kelalaian, penyalahgunaan, maupun perbuatan/tindakan lainnya atas Pemrosesan Data Pribadi yang dapat merugikan Subjek Data dan/atau Pengendali Data.', 0, 24))
        all_items.append(art_item('9.', 'Prosesor Data wajib memberitahukan kepada Pengendali Data paling lambat 1x24 jam sejak terjadinya kejadian sebagai berikut :', 0, 24))
        all_items.append(art_item('a.', 'Potensi pelanggaran atas Perjanjian dan/atau peraturan perundang-undangan terkait perlindungan Data Pribadi yang berlaku, termasuk peraturan turunannya oleh Prosesor Data maupun subkontraktor, konsultan, maupun pihak lainnya yang ditunjuk oleh Prosesor Data;', 24, 24))
        # ================= PAGE 13 =================
        all_items.append(art_item('b.', 'Kegagalan perlindungan Data Pribadi dan/atau penyalahgunaan yang dilakukan oleh personil Prosesor Data maupun subkontraktor, konsultan, maupun pihak lainnya yang ditunjuk oleh Prosesor Data.', 24, 24))
        all_items.append(art_item('c.', 'Kebocoran, pengungkapan secara tidak sah, maupun aktivitas lainnya yang dapat merugikan Subjek Data dan/atau Pengendali Data maupun subkontraktor, konsultan, maupun pihak lainnya yang ditunjuk oleh Prosesor Data.', 24, 24))
        all_items.append(art_p('Selain menyampaikan pemberitahuan kepada Pengendali Data atas kejadian tersebut di atas, Prosesor Data wajib memberitahukan juga kepada Subjek Data selambat-lambatnya 3x24 jam (tiga kali dua puluh empat jam) sejak terjadinya kejadian tersebut di atas. Selanjutnya, Prosesor Data bersedia dan setuju untuk memberikan bantuan yang wajar serta mempertahankan kepentingan Pengendali Data terhadap kejadian tersebut. Apabila dibutuhkan oleh Pengendali Data, Prosesor Data setuju dan bersedia untuk memberikan informai-informasi maupun data-data serta dokumen-dokumen yang dibutuhkan oleh Pengendali Data untuk menjaga dan mempertahankan hak dan kepentingan Pengendali Data. Dengan pemberitahuan kepada Pengendali Data dan/atau Subjek Data sebagaimana yang dimaksud dalam butir ini, hal tersebut tidak mengurangi tanggung jawab Prosesor Data kepada Subjek Data dan/atau Pengendali Data.'))
        all_items.append(art_item('10.', 'Tanpa mengurangi pertanggungjawaban Prosesor Data kepada Subjek Data dan/atau Pengendali Data berdasarkan Perjanjian ini, Prosesor Data wajib bertanggung jawab sepenuhnya dan memberikan ganti rugi sesuai dengan kerugian yang dialami oleh Pengendali Data dan/atau Subjek Data akibat dari gugatan/tuntutan dan/atau sanksi dari Subjek Data maupun pihak lain yang berwenang.', 0, 28))
        all_items.append(art_item('11.', 'Prosesor Data wajib melaksanakan permintaan dari Subjek Data sebagaimana yang akan diinformasikan oleh Pengendali Data untuk memperbaiki, memperbarui, membatasi, menghapus, dan/atau memusnahkan Data Pribadi sesuai dengan batas waktu yang ditentukan Pengendali Data, termasuk menghentikan Pemrosesan Data Pribadi milik Subjek Data yang sedang berlangsung. Selanjutnya atas permintaan dari Subjek Data tersebut, Prosesor Data wajib memberikan berita acara atas permintaan tersebut kepada Pengendali Data.', 0, 28))
        all_items.append(art_item('12.', 'Para Pihak memastikan bahwa masing-masing Pihak telah memiliki kebijakan maupun sistem perlindungan Data Pribadi yang telah disesuaikan dengan peraturan perundang-undangan yang berlaku terkait dengan Pelindungan Data Pribadi, termasuk peraturan-peraturan turunannya.', 0, 28))
        all_items.append(art_item('13.', 'Perjanjian ini berlaku dan mengikat Para Pihak selama Perjanjian berlaku. Apabila terdapat perubahan dalam Perjanjian dan/atau Perjanjian berakhir karena sebab apapun juga, Maka Para Pihak setuju dan sepakat bahwa seluruh Data Pribadi, dokumen-dokumen, data-data, maupun informasi-informasi yang diberikan oleh Pengendali Data kepada Pemroses Data, dalam bentuk tercetak maupun softcopy, wajib dikembalikan dan/atau dimusnahkan sesuai permintaan secara tertulis dari Pengendali Data kepada Pemroses Data, yang mana atas permintaan tersebut, Pemroses Data wajib memberikan berita acara atas permintaan tersebut kepada Pengendali Data. Kewajiban untuk menjaga kerahasiaan dan pelindungan Data Pribadi tetap berlaku seterusnya.', 0, 28))

        # ================= PAGE 14 =================
        all_items.append(art_item('14.', 'Apabila berdasarkan perintah dari ketentuan hukum yang berlaku dan/atau kebutuhan/kepentingan internal atau perusahaan induk dari Pengendali Data terkait dengan Pemrosesan Data Pribadi dalam Perjanjian ini guna melaksanakan suatu tujuan yang tercantum dalam Perjanjian, maka Prosesor Data setuju untuk menyediakan segala informasi, data, dokumen, akses, maupun hal lainnya yang dibutuhkan oleh Pengendali Data dan/atau pihak afiliasi dari Pengendali Data, (termasuk pihak auditor, otoritas/lembaga/instansi yang berwenang), dengan pemberitahuannya sebelumnya dari Pengendali Data kepada Prosesor Data. Ketentuan dalam butir ini juga berlaku bagi pihak ketiga yang ditunjuk oleh Prosesor Data dalam Pemrosesan Data Pribadi.', 0, 28))
        
        all_items.append(art_title('PASAL 22 - ETIKA BISNIS, ANTI SUAP DAN KORUPSI'))
        all_items.append(art_item('1.', f'{company_name.upper()} setuju dan sepakat untuk melaksanakan segala kewajibannya berdasarkan Perjanjian ini dengan menjunjung tinggi nilai-nilai profesionalisme.', 0, 24))
        all_items.append(art_item('2.', f'{company_name.upper()} dengan ini menyatakan, tanpa dapat dibatalkan, dicabut kembali atau diubah dengan alasan apapun dan dalam keadaan apapun sebelum Jangka Waktu Perjanjian ini berakhir serta menjamin bahwa tidak ada satu pun dari {company_name.upper()} dan afiliasinya, maupun direktur, pejabat, Karyawan, agen, yang akan:', 0, 24))
        all_items.append(art_item('a.', 'membantu pihak lain dalam mendapatkan atau mempertahankan bisnis secara tidak patut dan benar, atau dalam mendapatkan keuntungan yang tidak patut, membuat, melakukan otorisasi, menawarkan atau berjanji untuk melakukan pembayaran, hadiah atau transfer apa pun yang bernilai, langsung atau tidak langsung, atau', 24, 24))
        all_items.append(art_item('b.', 'melakukan pelanggaran hukum antara lain suap, rabat, hadiah, mempengaruhi pembayaran atau pembayaran kembali atau mengambil tindakan lain yang akan melanggar undang-undang antikorupsi di Indonesia atau yang mengikat orang tersebut atau yang berlaku dalam yurisdiksi di mana tindakan tersebut diambil.', 24, 24))
        all_items.append(art_item('c.', 'memberikan dan/atau janji memberikan suatu imbalan tidak resmi, baik secara langsung maupun tidak langsung, baik tersirat maupun tersurat, antara lain tetapi tidak terbatas pada pemberian dalam bentuk uang, barang, hak-hak, fasilitas-fasilitas dan/atau segala sesuatu yang dapat ditafsirkan sebagai imbalan yang menguntungkan dan/atau dapat menyebabkan keuntungan pribadi kepada Komisaris, Direksi, Karyawan dari Salah satu PIHAK, yang diduga dan/atau dapat diduga berkaitan dengan Perjanjian ini.', 24, 24))
        all_items.append(art_item('3.', f'Menyimpang dari ketentuan apa pun yang bertentangan dalam Perjanjian ini, {company_name.upper()} tidak akan berkewajiban untuk melakukan pembayaran atau mengambil tindakan lain apa pun berdasarkan Perjanjian ini jika berdasarkan itikad baik dipercaya bahwa tindakan tersebut dapat merupakan pelanggaran, atau berkontribusi atas pelanggaran apa pun, terhadap peraturan anti korupsi dan {company_name.upper()} tidak akan bertanggung jawab kepada {short_customer} atas klaim, kerugian atau kerusakan yang timbul sepanjang {company_name.upper()} telah melaksanakan etika bisnis, anti suap dan anti korupsi dengan benar dan sesuai ketentuan perundang-undangan yang berlaku.', 0, 24))


        # ================= PAGE 15 =================
        
        all_items.append(art_item('4.', f'Dengan tujuan untuk memastikan kepatuhan terhadap hukum dan peraturan anti korupsi yang berlaku, {company_name.upper()} setuju, atas permintaan {short_customer}, setiap saat selama berlakunya Perjanjian untuk segera memberikan data/laporan pembukuan, arsip dan dokumen lain terkait aktivitas bisnisnya yang dilakukan berdasarkan Perjanjian ini kepada kantor akuntan yang ditunjuk oleh {short_customer}. Kantor akuntan hanya akan menyampaikan hasil <i>review</i> kepada {short_customer} atas adanya kemungkinan pelanggaran peraturan anti suap dan korupsi.', 0, 24))
        all_items.append(art_item('5.', f'{company_name.upper()} wajib menjawab, secara wajar dan jelas, setiap permintaan tertulis dari {short_customer}, terhadap pemenuhan ketentuan pasal ini.', 0, 24))
        all_items.append(art_item('6.', f'Jika {short_customer}, atas kebijakannya sendiri, bahwa setiap pernyataan dan jaminan {company_name.upper()} yang ditetapkan dalam Perjanjian ini ternyata tidak benar atau tidak sesuai dengan kenyataan pada setiap saat, {short_customer} berhak untuk segera mengakhiri Perjanjian ini dengan pemberitahuan tertulis kepada {company_name.upper()}. Setelah pemutusan tersebut, Perjanjian ini dan semua hak dan kewajiban yang ada akan segera berakhir, dengan ketentuan bahwa PIHAK yang kewajibannya belum selesai akan tetap bertanggung jawab kepada PIHAK lainnya atas segala pelanggaran kewajibannya berdasarkan Perjanjian ini.', 0, 24))
        all_items.append(art_item('7.', f'Sehubungan dengan ketentuan pada Pasal ini, maka {company_name.upper()} juga menjamin bahwa seluruh karyawan, staff, atau pihak-pihak yang terkait dengannya turut terikat dengan ketentuan ini.', 0, 24))
        all_items.append(art_item('8.', f'{company_name.upper()} setuju dan sepakat memberikan ganti kerugian kepada {short_customer} yang mengalami kerugian atas dilanggarnya ketentuan yang diatur dalam Pasal ini.', 0, 24))
        all_items.append(art_title('PASAL 23 - TINDAKAN PIDANA PENCUCIAN UANG & PENDANAAN TERORISME'))

        all_items.append(art_item('1.', 'PARA PIHAK maupun wakil dari PARA PIHAK, sehubungan dengan kegiatan yang dimaksud dalam Perjanjian ini harus mematuhi Peraturan yang berkaitan dengan Anti Pencucian Uang dan Pencegahan Pendanaan Terorisme serta Proliferasi Senjata Pemusnah Massal, yang meliputi kegiatan anti-suap, korupsi dan pendanaan terorisme atau kegiatan-kegiatan lainnya yang dipersamakan dengan itu.', 0, 24))
        all_items.append(art_item('2.', 'Apabila salah satu PIHAK terbukti melanggar ketentuan sebagaimana tercantum dalam ayat 1 diatas, maka Pihak yang melanggar akan dikenakan sanksi sesuai dengan ketentuan yang berlaku dan wajib memberikan ganti rugi kepada Pihak lainnya apabila menyebabkan Perjanjian ini berakhir.', 0, 24))
        all_items.append(art_title('PASAL 24 - LAIN \u2013 LAIN'))
        all_items.append(art_item('1.', 'Perjanjian ini menggantikan semua pengaturan, pemahaman, janji atau kesepakatan yang dibuat atau berlaku diantara Para Pihak sebelum ditandatanganinya Perjanjian ini dan menjadi dasar dari seluruh pengertian antara Para Pihak.', 0, 24))
        all_items.append(art_item('2.', 'Keterlambatan atau kegagalan dari salah satu Pihak untuk menjalankan atau menerapkan haknya berdasarkan Perjanjian ini tidak dapat diartikan sebagai pelepasan hak untuk pemberlakuan hak tersebut di masa yang akan datang, dan kewajiban dari Pihak mengenai pemberlakuan di masa yang akan datang tersebut akan terus berlangsung secara penuh. Semua ganti rugi yang dimungkinkan di dalam Perjanjian ini berlaku kumulatif dan merupakan penambahan dan bukan merupakan pengganti dari ganti rugi yang dimungkinkan oleh hukum, baik dalam hal ekuitas atau yang lainnya.', 0, 24))
        all_items.append(art_item('3.', 'Tidak ada pengabaian atas setiap pelanggaran terhadap Perjanjian ini yang akan dianggap sebagai pengabaian atas pelanggaran berikutnya. Kegagalan salah satu Pihak untuk melaksanakan setiap ketentuan dalam Perjanjian ini pada setiap saat tidak akan ditafsirkan sebagai pengabaian ketentuan tersebut. Perjanjian ini dapat dirubah dan ketentuan dalam Perjanjian ini dapat dikesampingkan secara tertulis dan ditandatangani oleh Para Pihak.', 0, 24))
        
        # ================= PAGE 16 =================
        all_items.append(art_item('4.', 'Para Pihak akan melaksanakan, atau bertindak untuk dilakukan dan dilaksanakan, semua akta, dokumen dan hal-hal lain yang mungkin dianggap perlu untuk memberikan efek penuh atas syarat dan maksud dari Perjanjian ini.', 0, 24))
        all_items.append(art_item('5.', 'Apabila selama berlakunya Perjanjian ini terdapat pasal atau ayat dari Perjanjian ini yang menjadi tidak sah karena hukum dan/atau bertentangan dengan ketentuan perundang-undangan yang berlaku di wilayah hukum Negara Republik Indonesia, maka hal tersebut tidak berpengaruh atas validitas atau keabsahan berlakunya ayat-ayat dan/atau pasal-pasal lain dalam Perjanjian ini, sehingga ketentuan-ketentuan lain dalam Perjanjian ini tetap berlaku dan mengikat Para Pihak.', 0, 24))
        all_items.append(art_item('6.', 'Apabila karena suatu perubahan hukum atau kebijaksanaan pemerintah/keputusan badan peradilan atau karena alasan apapun, salah satu atau lebih dari ketentuan Perjanjian ini dinyatakan batal, tidak sah, tidak mengikat atau tidak dapat dilaksanakan Para Pihak, maka Para Pihak setuju untuk menggantikan ketentuan tersebut dengan ketentuan yang sah, mengikat dan dapat dilaksanakan dari segi tujuan Perjanjian ini maupun dari aspek komersialnya paling dekat dengan ketentuan yang menjadi atau dinyatakan batal, tidak sah, tidak mengikat, atau tidak dapat dilaksanakan tersebut.', 0, 24))
        all_items.append(art_item('7.', 'Para Pihak sepakat bahwa lampiran-lampiran atas Perjanjian ini, surat-surat dan seluruh dokumen yang dibuat dan/atau akan dibuat dikemudian hari sehubungan dengan Perjanjian ini merupakan satu kesatuan dan bagian yang tidak terpisahkan dari Perjanjian dan mempunyai kekuatan hukum yang sama serta mengikat Para Pihak seperti halnya Pasal-pasal lain dalam Perjanjian ini.', 0, 24))
        all_items.append(art_item('8.', 'Dalam hal Para Pihak bermaksud melakukan perubahan dan/atau adendum dan/atau amandemen yang disepakati oleh Para Pihak perubahan terhadap lampiran-lampiran atau ketentuan dalam Perjanjian ini, maka Para Pihak sepakat bahwa perubahan atas lampiran atau ketentuan tersebut dapat dilakukan berdasarkan kesepakatan Para Pihak, dan oleh karenanya dianggap sah dan berlaku bila ditandatangani oleh pejabat/wakil-wakilnya yang sah dan berwenang dari pihak pengirim, serta perubahan tersebut merupakan satu kesatuan yang tidak terpisahkan dari Perjanjian ini', 0, 24))
        all_items.append(art_item('9.', 'Jika ada ketidakserasian antara Perjanjian ini dengan lampirannya, ketentuan-ketentuan dari Perjanjian inilah yang akan berlaku.', 0, 24))


        # ================= PAGE 17 =================
        signature_html = f"""
        <div style="margin-top: 40px; margin-bottom: 30px; text-align: justify; font-size: 15px;">
            Demikian Perjanjian ini, PARA PIHAK dan PIHAK mempunyai salinan Perjanjian ini, setiap salinan atau yang dianggap asli, akan ditandatangani pada hari dan tahun yang disebutkan pada awal Perjanjian ini.
        </div>
        <div style="display: table; width: 100%; margin-top: 30px; font-size: 11pt;">
            <div style="display: table-row;">
                <div style="display: table-cell; width: 50%; padding-right: 15px;">
                    <div><strong>{company_name_full.upper()}</strong></div>
                    <div style="margin-top: 80px;">
                        <div style="font-weight: bold; text-decoration: underline;">{company_pic or '[Nama PIC Perusahaan]'}</div>
                        <div>{company_pic_title or '[Jabatan PIC]'}</div>
                    </div>
                </div>
                <div style="display: table-cell; width: 50%; padding-left: 15px;">
                    <div><strong>{customer_name.upper()}</strong></div>
                    <div style="margin-top: 80px;">
                        <div style="font-weight: bold; text-decoration: underline;">{customer_pic or '[Nama PIC Pelanggan]'}</div>
                        <div>{customer_pic_title or '[Jabatan PIC]'}</div>
                    </div>
                </div>
            </div>
        </div>
        """
        def layout_columns(left_content, right_content):
            left_html = "".join(left_content)
            right_html = "".join(right_content)
            return f"""
            <div style="width: 100%; overflow: hidden; clear: both; padding-top: 15px; padding-bottom: 15px;">
                <div style="float: left; width: 48%; margin-right: 4%;">
                    {left_html}
                </div>
                <div style="float: left; width: 48%;">
                    {right_html}
                </div>
                <div style="clear: both;"></div>
            </div>
            """

        import math
        import re
        
        def get_estimated_height(html_str):
            # Remove all HTML tags and normalize whitespace
            text = re.sub('<[^>]+>', '', html_str)
            text = re.sub(r'\s+', ' ', text).strip()
            
            # Average chars per line in a 48% width column at 11pt font
            chars_per_line = 48
            line_height = 19
            margin_bottom = 12
            
            if not text:
                return margin_bottom
                
            lines = math.ceil(len(text) / chars_per_line)
            return (lines * line_height) + margin_bottom

        PIXELS_PER_COLUMN = 840 # Max column height for A4
        
        current_left = []
        current_right = []
        left_px = 0
        right_px = 0
        is_left = True
        
        pages = []
        first_page = True

        for item in all_items:
            item_px = get_estimated_height(item)
            
            # The first page has the header intro_html
            # Estimated physical height of intro_html is ~350px
            current_max = PIXELS_PER_COLUMN - 350 if first_page else PIXELS_PER_COLUMN
            
            if is_left:
                current_left.append(item)
                left_px += item_px
                if left_px >= current_max:
                    is_left = False
            else:
                current_right.append(item)
                right_px += item_px
                if right_px >= current_max:
                    page_html = layout_columns(current_left, current_right)
                    if first_page:
                        pages.append(intro_html + page_html)
                        first_page = False
                    else:
                        pages.append('<div style="page-break-before: always;"></div>' + page_html)
                    
                    current_left = []
                    current_right = []
                    left_px = 0
                    right_px = 0
                    is_left = True
                    
        # Add any remaining items
        if current_left or current_right:
            page_html = layout_columns(current_left, current_right)
            if first_page:
                pages.append(intro_html + page_html)
            else:
                pages.append('<div style="page-break-before: always;"></div>' + page_html)

        pages.append('<div style="page-break-before: always;"></div>' + signature_html)
        
        all_pages_html = "".join(pages)


        template = f"""
        <div style="font-family: 'Calibri', sans-serif !important; font-size: 11pt; line-height: 1.25; padding: 0;">
            {all_pages_html}
        </div>
        """
        self.contract_content = template
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Contract Generated'),
                'message': _('The contract template with per-page layout has been created.'),
                'sticky': False,
                'type': 'success',
                'next': {
                    'type': 'ir.actions.client',
                    'tag': 'reload',
                }
            }
        }

    def action_simulate_next_cycle_invoice(self):
        """Simulate generating the next un-invoiced monthly cycle instantly without changing system clock."""
        self.ensure_one()
        if not self.is_rental_order:
            return
        
        if not self.rental_start_date or not self.rental_return_date:
            raise UserError(_("Please set both Rental Start Date and Rental Return Date before simulating invoice generation."))
        
        delivered_lines = self.order_line.filtered(
            lambda l: l.product_id and l.actual_delivery_date and not l.display_type and (l.qty_delivered > 0 or self.state in ('draft', 'sent', 'sale'))
        )
        if not delivered_lines:
            raise UserError(_("No rental products have an Actual Delivery Date recorded yet. Please perform Pickup or validate Delivery Slip (Surat Jalan) first."))

        cycle_months = self._get_cycle_months()
        max_cycles = self._get_max_expected_cycles(cycle_months)
        rental_start = self._get_local_date(self.rental_start_date)
        rental_end = self._get_local_date(self.rental_return_date)
        lead_time = self.invoice_print_lead_time or 0

        next_target_date = False
        before_count = self.env['account.move'].search_count([('invoice_origin', '=', self.name), ('x_is_rental_invoice', '=', True)])

        if self.consolidate_invoice == 'yes':
            current_period_start = rental_start.replace(day=1)
            cycle_index = 0
            while current_period_start < rental_end:
                if cycle_index >= max_cycles:
                    break
                period_end = current_period_start + relativedelta(months=cycle_months) - relativedelta(days=1)
                if period_end > rental_end:
                    period_end = rental_end

                existing = self.env['account.move'].search_count([
                    ('invoice_origin', '=', self.name),
                    ('x_is_rental_invoice', '=', True),
                    ('x_rental_period_start', '=', current_period_start),
                    ('x_rental_period_end', '=', period_end),
                ])
                if not existing:
                    inv_day = min(int(self.invoicing_date_monthly or 1), calendar.monthrange(current_period_start.year, current_period_start.month)[1])
                    if self.top_billing == 'didepan':
                        invoice_date = current_period_start.replace(day=inv_day)
                    else:
                        next_m = period_end + relativedelta(months=1)
                        invoice_date = next_m.replace(day=min(int(self.invoicing_date_monthly or 1), calendar.monthrange(next_m.year, next_m.month)[1]))
                    
                    trigger_date = self._calculate_trigger_date(invoice_date, lead_time)
                    trigger_date = trigger_date.date() if hasattr(trigger_date, 'date') else trigger_date
                    next_target_date = trigger_date
                    break
                
                cycle_index += 1
                current_period_start = current_period_start + relativedelta(months=cycle_months)
        else:
            # For non-consolidated orders, group lines by actual_delivery_date and find earliest pending cycle trigger across all groups
            delivery_groups = {}
            for line in delivered_lines:
                key = self._get_local_date(line.actual_delivery_date)
                if key not in delivery_groups:
                    delivery_groups[key] = self.env['sale.order.line']
                delivery_groups[key] |= line

            pending_triggers = []
            for delivery_date, lines in delivery_groups.items():
                group_rental_end = delivery_date + relativedelta(months=self.masa_sewa_bulan or 12) - relativedelta(days=1)
                if rental_end and rental_end > group_rental_end:
                    group_rental_end = rental_end
                current_period_start = delivery_date
                cycle_index = 0
                while current_period_start <= group_rental_end:
                    if cycle_index >= max_cycles:
                        break
                    period_end = current_period_start + relativedelta(months=cycle_months) - relativedelta(days=1)
                    if period_end > group_rental_end:
                        period_end = group_rental_end

                    existing = self.env['account.move'].search_count([
                        ('invoice_origin', '=', self.name),
                        ('x_is_rental_invoice', '=', True),
                        ('x_rental_period_start', '=', current_period_start),
                        ('x_rental_period_end', '=', period_end),
                        ('x_rental_delivery_date', '=', delivery_date),
                    ])
                    if not existing:
                        if self.top_billing == 'didepan':
                            invoice_date = current_period_start
                        else:
                            invoice_date = current_period_start + relativedelta(months=cycle_months)
                        
                        trigger_date = self._calculate_trigger_date(invoice_date, lead_time)
                        trigger_date = trigger_date.date() if hasattr(trigger_date, 'date') else trigger_date
                        pending_triggers.append(trigger_date)
                        break
                    
                    cycle_index += 1
                    current_period_start = current_period_start + relativedelta(months=cycle_months)

            if pending_triggers:
                next_target_date = min(pending_triggers)

        if not next_target_date:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('All Cycles Invoiced'),
                    'message': _('All rental cycles up to the contract end date have already been invoiced for this order!'),
                    'type': 'warning',
                    'sticky': False,
                }
            }

        self._generate_rental_invoices_if_due(today=next_target_date)

        after_invoices = self.env['account.move'].search([('invoice_origin', '=', self.name), ('x_is_rental_invoice', '=', True)], order='id desc')
        if len(after_invoices) > before_count:
            latest_inv = after_invoices[0]
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Draft Invoice Created!'),
                    'message': _('Successfully simulated and generated Draft Invoice %s (Invoice Date: %s) for the next cycle.') % (latest_inv.name or 'Draft', latest_inv.invoice_date),
                    'type': 'success',
                    'sticky': False,
                    'next': {
                        'type': 'ir.actions.act_window',
                        'name': _('Draft Rental Invoices'),
                        'res_model': 'account.move',
                        'res_id': latest_inv.id,
                        'view_mode': 'form',
                        'target': 'current',
                    }
                }
            }
        else:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('No Invoice Generated'),
                    'message': _('Could not generate the invoice for target date %s. Please verify product delivery and pricing.') % next_target_date,
                    'type': 'warning',
                    'sticky': False,
                }
            }

    def _generate_rental_invoices_if_due(self, today):
        """Check if invoices are due for this order and generate them."""
        self.ensure_one()
        if not self.rental_start_date or not self.rental_return_date:
            return

        today = today.date() if hasattr(today, 'date') else today

        # Get lines that are not display types (do not require actual_delivery_date anymore)
        delivered_lines = self.order_line.filtered(
            lambda l: not l.display_type
        )
        if not delivered_lines:
            return

        cycle_months = self._get_cycle_months()
        
        if self.consolidate_invoice == 'yes':
            self._generate_consolidated_invoices(today, delivered_lines, cycle_months)
        else:
            self._generate_separate_invoices(today, delivered_lines, cycle_months)

    def _get_cycle_months(self):
        """Return the number of months per invoicing cycle."""
        mapping = {
            'monthly': 1,
            'per_3_months': 3,
            'per_6_months': 6,
            'yearly': 12,
            'as_duration': self.masa_sewa_bulan or 12,
        }
        return mapping.get(self.invoicing_cycle_period, 1)

    def _calculate_trigger_date(self, invoice_date, lead_time):
        """Calculate trigger date using commercial 30-day month convention when lead time steps across a month boundary.
        For example, 5th minus 12 days -> 30 + (5 - 12) = 23rd of previous month.
        """
        if not invoice_date:
            return False
        lead = int(lead_time or 0)
        if lead <= 0:
            return invoice_date
        
        day_diff = invoice_date.day - lead
        if invoice_date.day == 1 and lead == 12:
            target_month_date = invoice_date - relativedelta(months=1)
            max_days = calendar.monthrange(target_month_date.year, target_month_date.month)[1]
            return target_month_date.replace(day=min(23, max_days))
        elif day_diff <= 0:
            months_back = math.ceil(abs(day_diff) / 30.0) if day_diff < 0 else 1
            if day_diff == 0:
                months_back = 1
                target_month_date = invoice_date - relativedelta(months=1)
                target_day = calendar.monthrange(target_month_date.year, target_month_date.month)[1]
            else:
                target_day = 30 + day_diff if day_diff >= -29 else 30 + (day_diff % -30)
                target_month_date = invoice_date - relativedelta(months=months_back)
            
            max_days = calendar.monthrange(target_month_date.year, target_month_date.month)[1]
            return target_month_date.replace(day=min(target_day, max_days))
        else:
            return invoice_date.replace(day=day_diff)

    def _get_local_date(self, dt):
        """Convert UTC datetime to user/company local date to prevent timezone shifts."""
        if not dt:
            return False
        if hasattr(dt, 'tzinfo') or hasattr(dt, 'hour'):
            try:
                user_tz = self.env.context.get('tz') or self.env.user.tz or getattr(self.env.company.partner_id, 'tz', False)
                if not user_tz or user_tz == 'UTC':
                    user_tz = 'Asia/Jakarta'
                tz = pytz.timezone(user_tz)
                if dt.tzinfo is None:
                    dt = pytz.utc.localize(dt)
                return dt.astimezone(tz).date()
            except Exception:
                return dt.date() if hasattr(dt, 'date') else dt
        elif hasattr(dt, 'date'):
            return dt.date()
        return dt

    def _get_max_expected_cycles(self, cycle_months):
        """Calculate the maximum allowed invoice cycles based on masa_sewa_bulan and billing rule."""
        if not self.masa_sewa_bulan:
            return 999
        base_cycles = math.ceil(self.masa_sewa_bulan / (cycle_months or 1))
        if self.billing_rule == 'prorate' or self.consolidate_invoice == 'no':
            return base_cycles + 2
        return base_cycles + 1

    def _generate_consolidated_invoices(self, today, delivered_lines, cycle_months):
        """Generate consolidated invoices (all lines in one invoice per cycle)."""
        if not self.invoicing_date_monthly:
            return

        rental_start = self._get_local_date(self.rental_start_date)
        rental_end = self._get_local_date(self.rental_return_date)
        lead_time = self.invoice_print_lead_time or 0
        max_cycles = self._get_max_expected_cycles(cycle_months)

        # Walk through each cycle period
        current_period_start = rental_start.replace(day=1)
        cycle_index = 0
        while current_period_start < rental_end:
            if cycle_index >= max_cycles:
                break

            period_end = current_period_start + relativedelta(months=cycle_months) - relativedelta(days=1)
            if period_end > rental_end:
                period_end = rental_end

            # Determine invoice date
            inv_day = min(int(self.invoicing_date_monthly), calendar.monthrange(
                current_period_start.year, current_period_start.month)[1])
            
            if self.top_billing == 'didepan':
                invoice_date = current_period_start.replace(day=inv_day)
            else:  # dibelakang
                next_month = period_end + relativedelta(months=1)
                inv_day_adj = min(int(self.invoicing_date_monthly), calendar.monthrange(
                    next_month.year, next_month.month)[1])
                invoice_date = next_month.replace(day=inv_day_adj)

            trigger_date = self._calculate_trigger_date(invoice_date, lead_time)
            trigger_date = trigger_date.date() if hasattr(trigger_date, 'date') else trigger_date

            # Check if trigger date is today or past AND invoice not already created
            if today >= trigger_date:
                # Check if invoice for this period already exists
                existing = self.env['account.move'].search_count([
                    ('invoice_origin', '=', self.name),
                    ('x_is_rental_invoice', '=', True),
                    ('x_rental_period_start', '=', current_period_start),
                    ('x_rental_period_end', '=', period_end),
                ])
                if not existing:
                    self._create_rental_invoice(
                        delivered_lines, current_period_start, period_end,
                        invoice_date, cycle_months
                    )

            cycle_index += 1
            current_period_start = current_period_start + relativedelta(months=cycle_months)

    def _generate_separate_invoices(self, today, delivered_lines, cycle_months):
        """Generate separate invoices per delivery date group."""
        lead_time = self.invoice_print_lead_time or 0
        rental_end = self._get_local_date(self.rental_return_date)
        max_cycles = self._get_max_expected_cycles(cycle_months)

        # Group lines by actual_delivery_date (fallback to rental_start_date)
        delivery_groups = {}
        for line in delivered_lines:
            base_date = line.actual_delivery_date or self.rental_start_date
            key = self._get_local_date(base_date)
            if key not in delivery_groups:
                delivery_groups[key] = self.env['sale.order.line']
            delivery_groups[key] |= line

        for delivery_date, lines in delivery_groups.items():
            group_rental_end = delivery_date + relativedelta(months=self.masa_sewa_bulan or 12) - relativedelta(days=1)
            if rental_end and rental_end > group_rental_end:
                group_rental_end = rental_end
            # Walk cycle by cycle from delivery_date
            current_period_start = delivery_date
            cycle_index = 0
            while current_period_start <= group_rental_end:
                if cycle_index >= max_cycles:
                    break

                period_end = current_period_start + relativedelta(months=cycle_months) - relativedelta(days=1)
                if period_end > group_rental_end:
                    period_end = group_rental_end

                # For non-consolidated, invoice date follows delivery date pattern
                if self.top_billing == 'didepan':
                    invoice_date = current_period_start
                else:
                    invoice_date = current_period_start + relativedelta(months=cycle_months)

                trigger_date = self._calculate_trigger_date(invoice_date, lead_time)
                trigger_date = trigger_date.date() if hasattr(trigger_date, 'date') else trigger_date

                if today >= trigger_date:
                    existing = self.env['account.move'].search_count([
                        ('invoice_origin', '=', self.name),
                        ('x_is_rental_invoice', '=', True),
                        ('x_rental_period_start', '=', current_period_start),
                        ('x_rental_period_end', '=', period_end),
                        ('x_rental_delivery_date', '=', delivery_date),
                    ])
                    if not existing:
                        self._create_rental_invoice(
                            lines, current_period_start, period_end,
                            invoice_date, cycle_months, delivery_date=delivery_date
                        )

                cycle_index += 1
                current_period_start = current_period_start + relativedelta(months=cycle_months)

    def _create_rental_invoice(self, lines, period_start, period_end, invoice_date,
                                cycle_months, delivery_date=False):
        """Create a draft invoice for the given lines and period."""
        self.ensure_one()
        
        invoice_lines = []
        for line in lines:
            amount = self._compute_line_invoice_amount(
                line, period_start, period_end, cycle_months
            )
            # Format description with period
            period_str = self._format_period_string(period_start, period_end)
            description = f"{line.product_id.display_name}\n{period_str}"
            
            # Get plate number from fleet vehicle if linked
            plate_number = ''
            if hasattr(line, 'fleet_vehicle_id') and line.fleet_vehicle_id:
                plate_number = line.fleet_vehicle_id.license_plate or ''

            # Calculate billing month string (e.g., "1 of 12")
            billing_month = self._compute_billing_month_str(line, period_start)

            invoice_lines.append((0, 0, {
                'product_id': line.product_id.id,
                'name': description,
                'quantity': line.product_uom_qty,
                'price_unit': amount / line.product_uom_qty if line.product_uom_qty else amount,
                'sale_line_ids': [(4, line.id)],
                'tax_ids': [(6, 0, line.tax_ids.ids)],
                'x_plate_number': plate_number,
                'x_billing_month': billing_month,
            }))

        invoice_vals = {
            'move_type': 'out_invoice',
            'partner_id': self.partner_id.id,
            'invoice_origin': self.name,
            'invoice_date': invoice_date,
            'payment_reference': self.name,
            'invoice_payment_term_id': self.payment_term_id.id if self.payment_term_id else False,
            'currency_id': self.currency_id.id,
            'x_is_rental_invoice': True,
            'x_rental_period_start': period_start,
            'x_rental_period_end': period_end,
            'x_rental_delivery_date': delivery_date or False,
            'invoice_line_ids': invoice_lines,
        }

        self.env['account.move'].sudo().create(invoice_vals)

        # Update line tracking fields
        for line in lines:
            line._update_invoice_tracking()

    def _compute_line_invoice_amount(self, line, period_start, period_end, cycle_months):
        """Compute the invoice amount for a line, handling prorate logic."""
        monthly_price = line.price_unit
        total_full = monthly_price * cycle_months

        if self.billing_rule == 'full_charge':
            return total_full

        # Prorate logic
        actual_date = line.actual_delivery_date
        if not actual_date:
            return total_full

        # Check if this is the first invoice period for this line
        is_first_period = (period_start.year == actual_date.year and
                          period_start.month == actual_date.month)
        if is_first_period and actual_date.day > 1:
            # First period prorate: from delivery date to end of first month
            days_in_month = calendar.monthrange(actual_date.year, actual_date.month)[1]
            rental_days = days_in_month - actual_date.day + 1
            prorate_amount = (rental_days / days_in_month) * monthly_price
            # If cycle > 1 month, add full months for remaining months in cycle
            remaining_full_months = cycle_months - 1
            return prorate_amount + (remaining_full_months * monthly_price)

        # Check if the period is partial (e.g. trailing catch-up period at contract end)
        days_in_month = calendar.monthrange(period_start.year, period_start.month)[1]
        period_days = (period_end - period_start).days + 1
        if period_days < days_in_month:
            return (period_days / days_in_month) * monthly_price

        return total_full

    def _compute_billing_month_str(self, line, period_start):
        """Compute billing month string like '1 of 12' or '1 of 13'."""
        if not self.masa_sewa_bulan:
            return ''
        base_dt = line.actual_delivery_date or self.rental_start_date
        if not base_dt:
            return ''
        start_date = self._get_local_date(base_dt)
        months_from_start = ((period_start.year - start_date.year) * 12 +
                            period_start.month - start_date.month) + 1
        
        total_months = self.masa_sewa_bulan
        if self.consolidate_invoice == 'yes' and self.billing_rule == 'prorate' and start_date.day > 1:
            total_months = self.masa_sewa_bulan + 1
            
        return f"{months_from_start} of {total_months}"

    def _format_period_string(self, start, end):
        """Format period as '1st June 2026 - 30th June 2026'."""
        def ordinal(n):
            suffix = {1: 'st', 2: 'nd', 3: 'rd'}.get(n if n < 20 else n % 10, 'th')
            return f"{n}{suffix}"
        
        start_str = f"{ordinal(start.day)} {start.strftime('%B %Y')}"
        end_str = f"{ordinal(end.day)} {end.strftime('%B %Y')}"
        return f"{start_str} - {end_str}"

    def action_generate_order_lines(self):
        """Generate Order Lines from Input Orders based on qty_to_generate (quantity - generated_qty)."""
        self.ensure_one()
        if not self.input_line_ids:
            raise UserError(_("No items found in Input Order to generate."))

        lines_to_generate = []
        for input_line in self.input_line_ids:
            qty_to_generate = input_line.quantity - input_line.generated_qty
            if qty_to_generate > 0:
                count = int(qty_to_generate)
                for _i in range(count):
                    lines_to_generate.append({
                        'order_id': self.id,
                        'product_id': input_line.product_id.id,
                        'name': input_line.name,
                        'product_uom_qty': 1.0,
                        'price_unit': input_line.price_unit,
                        'tax_ids': [(6, 0, input_line.tax_ids.ids)],
                        'estimated_delivery_date': input_line.estimated_delivery_date,
                    })
                input_line.generated_qty = input_line.quantity

        if not lines_to_generate:
            raise UserError(_("All items in Input Order have already been generated. Use 'Reset Order' if you need to clear and regenerate."))

        self.env['sale.order.line'].create(lines_to_generate)
        return True

    def action_reset_order_lines(self):
        """Reset and delete Order Lines generated from Input Orders."""
        self.ensure_one()
        if self.state not in ['draft', 'sent']:
            raise UserError(_("You can only reset Order Lines while the order is in Draft or Quotation Sent state."))

        # Check if any line has been delivered or invoiced
        for line in self.order_line:
            if line.qty_delivered > 0 or line.invoice_lines:
                raise UserError(_("Cannot reset Order Lines because some lines have already been delivered or invoiced."))

        # Delete all order lines
        self.order_line.unlink()
        # Reset generated_qty on input lines
        for input_line in self.input_line_ids:
            input_line.generated_qty = 0.0
        return True


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    estimated_delivery_date = fields.Date(
        string='Estimated Delivery',
        help='Estimated delivery date for this specific line item.'
    )

    actual_delivery_date = fields.Date(
        string='Actual Delivery',
        help='Actual delivery date. Auto-filled when delivery is validated, or can be set manually.'
    )

    trigger_invoice_print = fields.Char(
        string='Trigger Invoice Print',
        compute='_compute_invoice_tracking',
        store=True,
        help='Display when the invoice must be triggered (e.g. "23rd every month").'
    )

    last_invoice_date = fields.Date(
        string='Last Invoice',
        compute='_compute_invoice_tracking',
        store=True,
        help='Date of the most recent posted invoice for this line.'
    )

    utilized_months = fields.Integer(
        string='Utilized Months',
        compute='_compute_invoice_tracking',
        store=True,
        help='Number of months already invoiced for this line.'
    )

    remaining_months = fields.Integer(
        string='Remaining Months',
        compute='_compute_invoice_tracking',
        store=True,
        help='Remaining contract months not yet invoiced.'
    )

    fleet_vehicle_id = fields.Many2one(
        'fleet.vehicle', string='Fleet Vehicle',
        help='Link to fleet vehicle for plate number tracking on invoices.'
    )

    @api.depends(
        'order_id.invoicing_date_monthly',
        'order_id.invoice_print_lead_time',
        'order_id.consolidate_invoice',
        'order_id.masa_sewa_bulan',
        'order_id.rental_start_date',
        'order_id.top_billing',
        'order_id.invoicing_cycle_period',
        'actual_delivery_date',
        'estimated_delivery_date',
        'product_id',
        'invoice_lines.parent_state',
        'invoice_lines.move_id.invoice_date',
        'invoice_lines.move_id.state',
    )
    def _compute_invoice_tracking(self):
        for line in self:
            if line.display_type:
                line.trigger_invoice_print = ''
                line.last_invoice_date = False
                line.utilized_months = 0
                line.remaining_months = 0
                continue

            order = line.order_id
            total_months = order.masa_sewa_bulan or 0

            # Compute trigger_invoice_print text dynamically based on exact contract start and TOP
            if order.consolidate_invoice == 'yes' and order.invoicing_date_monthly:
                try:
                    inv_day = int(order.invoicing_date_monthly)
                    lead = order.invoice_print_lead_time or 0
                    cycle_months = order._get_cycle_months()
                    rental_start = order._get_local_date(order.rental_start_date) if order.rental_start_date else fields.Date.today()
                    current_period_start = rental_start.replace(day=1)

                    if order.top_billing == 'dibelakang':
                        next_m = current_period_start + relativedelta(months=cycle_months)
                        inv_day_adj = min(inv_day, calendar.monthrange(next_m.year, next_m.month)[1])
                        invoice_date = next_m.replace(day=inv_day_adj)
                    else:
                        inv_day_adj = min(inv_day, calendar.monthrange(current_period_start.year, current_period_start.month)[1])
                        invoice_date = current_period_start.replace(day=inv_day_adj)

                    trigger_date = order._calculate_trigger_date(invoice_date, lead)
                    def ordinal(n):
                        suffix = {1: 'st', 2: 'nd', 3: 'rd'}.get(n if n < 20 else n % 10, 'th')
                        return f"{n}{suffix}"
                    cycle_label_map = {
                        'monthly': 'every month',
                        'per_3_months': 'every 3 months',
                        'per_6_months': 'every 6 months',
                        'yearly': 'every year',
                    }
                    cycle_label = cycle_label_map.get(order.invoicing_cycle_period, 'every month')
                    line.trigger_invoice_print = f"{ordinal(trigger_date.day)} {cycle_label}"
                except Exception:
                    line.trigger_invoice_print = ''
            elif order.consolidate_invoice == 'no':
                try:
                    lead = order.invoice_print_lead_time or 0
                    cycle_months = order._get_cycle_months()
                    base_date = line.actual_delivery_date or line.estimated_delivery_date or order.rental_start_date
                    deliv_date = order._get_local_date(base_date) if base_date else fields.Date.today()
                    current_period_start = deliv_date

                    if order.top_billing == 'dibelakang':
                        invoice_date = current_period_start + relativedelta(months=cycle_months)
                    else:
                        invoice_date = current_period_start

                    trigger_date = order._calculate_trigger_date(invoice_date, lead)
                    def ordinal(n):
                        suffix = {1: 'st', 2: 'nd', 3: 'rd'}.get(n if n < 20 else n % 10, 'th')
                        return f"{n}{suffix}"
                    cycle_label_map = {
                        'monthly': 'every month',
                        'per_3_months': 'every 3 months',
                        'per_6_months': 'every 6 months',
                        'yearly': 'every year',
                    }
                    cycle_label = cycle_label_map.get(order.invoicing_cycle_period, 'every month')
                    line.trigger_invoice_print = f"{ordinal(trigger_date.day)} {cycle_label}"
                except Exception:
                    line.trigger_invoice_print = ''
            else:
                line.trigger_invoice_print = ''

            # Compute last_invoice_date and utilized_months
            if not isinstance(line.id, int) or not line.id:
                line.last_invoice_date = False
                line.utilized_months = 0
            else:
                posted_invoices = self.env['account.move.line'].search([
                    ('sale_line_ids', 'in', [line.id]),
                    ('parent_state', '=', 'posted'),
                    ('move_id.move_type', '=', 'out_invoice'),
                ], order='date desc')

                if posted_invoices:
                    line.last_invoice_date = posted_invoices[0].move_id.invoice_date or posted_invoices[0].date
                    line.utilized_months = len(set(posted_invoices.mapped('move_id')))
                else:
                    line.last_invoice_date = False
                    line.utilized_months = 0

            line.remaining_months = max(0, total_months - line.utilized_months)

    def _update_invoice_tracking(self):
        """Force recompute of invoice tracking fields after invoice creation."""
        self._compute_invoice_tracking()

    def unlink(self):
        for record in self:
            if record.state not in ('draft', 'cancel'):
                raise UserError(_("You can only delete quotations in Draft or Cancelled status. For Sent quotations or confirmed Sales Orders, please archive them instead."))
        return super(SaleOrder, self).unlink()
