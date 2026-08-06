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
        
        # Indonesian date formatting for header
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

        # Short name helper or initials
        short_customer = "".join([word[0] for word in customer_name.split() if word.isalpha() and len(word) > 1]).upper() or "PIHAK KEDUA"
        customer_address = self.partner_id.contact_address or _("Graha Mandiri Lt. 3A, Jl. Imam Bonjol No. 61 Menteng Jakarta Pusat 10310")
        
        # Contract numbers
        order_code = self.name.split('/')[-1] if self.name and '/' in self.name else (self.name or "0351")
        pks_cakrawala = f"No.{order_code}P/S/CRS/{roman_month}/{year_str}"
        pks_partner = f"No. 001A/PKS-LLI/{short_customer}/{roman_month}/{year_str}"

        template = f"""
        <div style="font-family: Arial, sans-serif; line-height: 1.6; padding: 20px;">
            <h3 style="text-align: center; margin-bottom: 2px;">PERJANJIAN SEWA</h3>
            <h4 style="text-align: center; margin-top: 2px; margin-bottom: 2px;">ANTARA</h4>
            <h3 style="text-align: center; margin-top: 2px; margin-bottom: 2px;">{company_name.upper()}</h3>
            <h4 style="text-align: center; margin-top: 2px; margin-bottom: 2px;">DENGAN</h4>
            <h3 style="text-align: center; margin-top: 2px; margin-bottom: 15px;">{customer_name.upper()}</h3>
            <p style="text-align: center; margin-bottom: 2px;"><strong>{pks_cakrawala}</strong></p>
            <p style="text-align: center; margin-top: 2px; margin-bottom: 20px;"><strong>{pks_partner}</strong></p>
            <hr style="border: none; border-top: 1px solid currentColor; margin-bottom: 20px;"/>
            <p>Perjanjian Sewa ini (selanjutnya disebut 'Perjanjian') dibuat pada hari ini, {tanggal_str} bertempat di Jakarta, oleh dan antara :</p>
            <ol>
                <li style="margin-bottom: 12px;"><strong>{company_name}</strong>, suatu badan hukum berbentuk perseroan terbatas yang didirikan menurut dan berdasarkan hukum negara Republik Indonesia, berkedudukan di Rukan The Fifty No.10 Jalan Arteri Kelapa Gading, Pegangsaan Dua Jakarta Utara bertindak diwakili oleh <strong>Bumina Elizabeth Tjhin</strong> selaku <strong>Direktur</strong> untuk dan atas nama {company_name}, (untuk selanjutnya disebut <strong>'CAKRAWALA'</strong>), dan</li>
                <li style="margin-bottom: 12px;"><strong>{customer_name}</strong> suatu badan hukum berbentuk perseroan terbatas yang didirikan menurut dan berdasarkan hukum negara Republik Indonesia, berkedudukan di {customer_address}, bertindak diwakili oleh <strong>[Nama Perwakilan]</strong> dalam kedudukannya sebagai <strong>[Jabatan Perwakilan]</strong> untuk dan atas nama {customer_name} (untuk selanjutnya disebut <strong>'{short_customer}'</strong>).</li>
            </ol>
            <p>CAKRAWALA dan {short_customer} selanjutnya disebut sebagai 'PARA PIHAK' dan 'PIHAK'.</p>
            <p>Bahwa:</p>
            <ol style="list-style-type: upper-alpha;">
                <li>CAKRAWALA menyediakan jasa penyewaan kendaraan kepada para pelanggannya.</li>
                <li>{short_customer} bermaksud untuk menyewa kendaraan tertentu dari CAKRAWALA.</li>
            </ol>
        </div>
        """
        self.contract_content = template
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Contract Generated'),
                'message': _('The general contract template has been created and populated below.'),
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

        # Get lines with actual delivery dates (delivery completed)
        delivered_lines = self.order_line.filtered(
            lambda l: l.actual_delivery_date and not l.display_type
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

        # Group lines by actual_delivery_date
        delivery_groups = {}
        for line in delivered_lines:
            key = self._get_local_date(line.actual_delivery_date)
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
