from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class ReplacementCar(models.Model):
    _name = 'replacement.car'
    _description = 'Replacement Car'
    _rec_name = 'name'
    _order = 'id desc'

    name = fields.Char(
        string="Reference",
        default='/',
        readonly=True
    )

    company_id = fields.Many2one(
        'res.company',
        string="Company Client",
        required=True,
        default=lambda self: self.env.company
    )

    vehicle_old_id = fields.Many2one(
        'fleet.vehicle',
        string="Broken Vehicle",
        required=True
    )

    vehicle_new_id = fields.Many2one(
        'fleet.vehicle',
        string="Replacement Vehicle"
    )
    
    spk_ids = fields.Many2many(
        'fleet.spk',
        string="SPK Reference",
        readonly=True
    )

    service_planning_id = fields.Many2one(
        'service.planning',
        string="Service Planning",
        ondelete='set null',
    )
    
    request_date = fields.Date(
        string="Request Date",
        default=fields.Date.today,
        required=True
    )
    
    pic_name = fields.Char(
        string="PIC Name",
        required=True
    )
    
    estimation_use_date = fields.Date(
        string="Estimation Use Date",
        required=True
    )

    reason = fields.Text(
        string="Reason"
    )


    
    old_license_plate = fields.Char(related='vehicle_old_id.fleet_document_license_plate', string="Old License Plate")
    old_vehicle_model_id = fields.Many2one('fleet.vehicle.model', related='vehicle_old_id.model_id', string="Old Vehicle Model")
    old_year = fields.Selection(related='vehicle_old_id.model_year', string="Old Year")
    old_color = fields.Char(related='vehicle_old_id.color', string="Old Color")

    new_company_client_id = fields.Many2one('res.company', related='vehicle_new_id.company_id', string="New Company Client")
    new_license_plate = fields.Char(related='vehicle_new_id.fleet_document_license_plate', string="New License Plate")
    new_vehicle_model_id = fields.Many2one('fleet.vehicle.model', related='vehicle_new_id.model_id', string="New Vehicle Model")
    new_year = fields.Selection(related='vehicle_new_id.model_year', string="New Year")
    new_color = fields.Char(related='vehicle_new_id.color', string="New Color")

    
    approval_line_ids = fields.One2many(
        'replacement.approval',
        'replacement_car_id',
        string="Approval Lines"
    )
    
    good_issue_id = fields.Many2one(
        'stock.picking',
        string="Good Issue",
        readonly=True
    )

    vendor_id = fields.Many2one(
        'res.partner',
        string='Vendor'
    )

    vendor_bill_id = fields.Many2one(
        'account.move',
        string='Vendor Bill',
        readonly=True
    )

    state = fields.Selection([
        ('draft', 'Draft'),
        ('waiting', 'Waiting Approval'),
        ('approved', 'Approved'),
        ('done', 'Done'),
        ('rejected', 'Rejected'),
    ], default='draft', tracking=True)

    can_approve = fields.Boolean(
        string="Current user can act",
        compute="_compute_can_approve",
    )

    @api.depends(
        "state",
        "approval_line_ids.state",
        "approval_line_ids.approver_id",
        "approval_line_ids.sequence",
    )
    def _compute_can_approve(self):
        user = self.env.user
        for rec in self:
            pending = rec.approval_line_ids.filtered(
                lambda l: l.state == "waiting"
            ).sorted("sequence")
            first = pending[:1]
            rec.can_approve = (
                rec.state == "waiting"
                and bool(first)
                and first.approver_id == user
            )

    def _get_next_waiting_approval_line(self):
        self.ensure_one()
        pending = self.approval_line_ids.filtered(
            lambda l: l.state == "waiting"
        ).sorted("sequence")
        return pending[:1]

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', '/') == '/':
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'replacement.car'
                ) or '/'
        return super().create(vals_list)

    @api.constrains('vehicle_old_id', 'vehicle_new_id')
    def _check_vehicle(self):
        for rec in self:
            if rec.vehicle_old_id and rec.vehicle_new_id:
                if rec.vehicle_old_id.id == rec.vehicle_new_id.id:
                    raise ValidationError(
                        "Replacement vehicle cannot be same as broken vehicle."
                    )
                
    def action_submit(self):
        for rec in self:
            rec._generate_approval_from_master()
            rec.state = 'waiting'

    def _generate_approval_from_master(self):
        """Copy master.approval (template) into replacement.approval for this document."""
        self.ensure_one()
        ApprovalLine = self.env['replacement.approval']
        ApprovalLine.search([('replacement_car_id', '=', self.id)]).unlink()
        templates = self.env['master.approval'].search([], order='sequence, id')
        if not templates:
            raise ValidationError(
                "Belum ada master approval. "
                "Isi daftar approver di menu Master Approval Replacement."
            )
        for tmpl in templates:
            if not tmpl.approver_id:
                raise ValidationError(
                    "Baris master approval urutan %s belum punya approver."
                    % (tmpl.sequence or tmpl.id)
                )
            ApprovalLine.create({
                'replacement_car_id': self.id,
                'sequence': tmpl.sequence,
                'approver_id': tmpl.approver_id.id,
                'state': 'waiting',
            })

    def action_approve(self):
        for rec in self:
            line = rec._get_next_waiting_approval_line()
            if not line:
                raise ValidationError(_("There is no approval step waiting."))
            if line.approver_id != self.env.user:
                raise ValidationError(_("Only the assigned approver can approve at this step."))
            line.write({
                "state": "approved",
                "approval_date": fields.Datetime.now(),
            })
            still_waiting = rec.approval_line_ids.filtered(
                lambda l: l.state == "waiting"
            )

            if still_waiting:
                rec.state = "waiting"
            else:
                rec.state = "approved"
                rec.action_create_good_issue()

    def action_done(self):

        for rec in self:

            if not rec.good_issue_id:
                raise ValidationError(
                    "Create Good Issue terlebih dahulu."
                )

            rec.state = 'done'

    def action_reject(self):
        for rec in self:
            line = rec._get_next_waiting_approval_line()
            if not line:
                raise ValidationError(_("There is no approval step waiting."))
            if line.approver_id != self.env.user:
                raise ValidationError(_("Only the assigned approver can reject at this step."))
            line.write({
                "state": "rejected",
                "reject_date": fields.Datetime.now(),
            })
            rec.state = "rejected"
    
    def action_create_good_issue(self):

        StockPicking = self.env['stock.picking']

        picking_type = self.env['stock.picking.type'].search([
            ('code', '=', 'outgoing')
        ], limit=1)

        if not picking_type:
            raise ValidationError("Outgoing picking type not found.")

        for rec in self:
            if rec.good_issue_id and rec.good_issue_id.state != 'cancel':
                raise ValidationError("Good Issue already created.")

            # 1. Cari Fleet Document yang aktif (state='open') untuk kendaraan lama
            fleet_document = rec.vehicle_old_id.running_fleet_document_id

            if not fleet_document:
                raise ValidationError(
                    "Kendaraan '%s' tidak memiliki Fleet Document yang aktif (Running).\n\n"
                    "Silakan buat dan aktifkan Fleet Document untuk kendaraan ini, "
                    "lalu pilih (centang) produk yang akan dikeluarkan di tab Products."
                    % rec.vehicle_old_id.display_name
                )

            # 2. Ambil hanya product lines yang selected=True
            selected_lines = fleet_document.line_ids.filtered(lambda l: l.selected)

            if not selected_lines:
                raise ValidationError(
                    "Tidak ada product yang dipilih (Select ☑) di Fleet Document '%s'.\n\n"
                    "Silakan buka Fleet Document kendaraan lama dan centang (select) "
                    "product yang akan dikeluarkan sebagai Good Issue."
                    % fleet_document.display_name
                )
            # 3. Siapkan info kendaraan lama untuk description_picking
            #    Data source paling benar:
            #    - Vehicle name: model_id.display_name (bukan full name yg terlalu panjang)
            #    - Serial Number: fleet_document_asset_number (computed dari Fleet Doc aktif)
            #    - License Plate: fleet_document_license_plate (computed dari Fleet Doc aktif)
            #    - Source SPK/PR: spk_ids linked ke RC ini
            #    - Analytic: vehicle_old_id.analytic_account_id
            vehicle = rec.vehicle_old_id

            # Vehicle: tampilkan nama model (misal "Volvo/FM" bukan "Volvo/FM/ODO-1347")
            vehicle_model = vehicle.model_id.display_name if vehicle.model_id else vehicle.display_name

            # Serial Number / Asset: ambil dari data kendaraan lama langsung
            serial_number = vehicle.vin_sn or vehicle.asset_number or ''

            # License Plate: ambil dari data kendaraan lama langsung
            license_plate = vehicle.license_plate or ''

            # Source RC: RC number
            rc_ref = rec.name or ''

            # Notes: alasan dari RC
            rc_notes = rec.reason or ''

            # 4. Build stock move lines dari selected products (multi-product support)
            move_lines = []
            for line in selected_lines:
                # Ambil analytic dari line produk Fleet Document
                line_analytic = line.analytic_account_id
                line_analytic_name = line_analytic.name if line_analytic else ''

                # Bangun description_picking secara dinamis untuk baris ini
                desc_parts = []
                if vehicle_model:
                    desc_parts.append(_("Vehicle: %s") % vehicle_model)
                if serial_number and str(serial_number).strip().lower() != 'false':
                    desc_parts.append(_("Serial Number: %s") % serial_number)
                if license_plate and str(license_plate).strip().lower() != 'false':
                    desc_parts.append(_("License Plate: %s") % license_plate)
                if rc_ref:
                    desc_parts.append(_("Source RC: %s") % rc_ref)
                if line_analytic_name and str(line_analytic_name).strip().lower() != 'false':
                    desc_parts.append(_("Analytic: %s") % line_analytic_name)
                if rc_notes and str(rc_notes).strip().lower() != 'false':
                    desc_parts.append(_("Notes: %s") % rc_notes)
                picking_description = "\n".join(desc_parts)

                # Siapkan analytic distribution jika ada
                # (field ini tersedia jika modul stock_account/analytic aktif)
                analytic_distribution = {}
                if line_analytic:
                    # Cek dulu apakah field tersedia di model stock.move
                    if 'analytic_distribution' in self.env['stock.move']._fields:
                        analytic_distribution = {str(line_analytic.id): 100}

                move_vals = {
                    'product_id': line.product_id.id,
                    'product_uom_qty': line.quantity or 1.0,
                    'product_uom': line.product_id.uom_id.id,
                    'location_id': picking_type.default_location_src_id.id,
                    'location_dest_id': picking_type.default_location_dest_id.id,
                    'description_picking': picking_description,
                }
                if analytic_distribution:
                    move_vals['analytic_distribution'] = analytic_distribution
                move_lines.append((0, 0, move_vals))

            # 5. Buat Delivery Order / Good Issue
            picking = StockPicking.create({
                'picking_type_id': picking_type.id,
                'origin': rec.name,
                'location_id': picking_type.default_location_src_id.id,
                'location_dest_id': picking_type.default_location_dest_id.id,
                'move_ids': move_lines,
            })

            picking.action_confirm()
            picking.action_assign()

            rec.good_issue_id = picking.id



    def action_reset_to_draft(self):
        for rec in self:
            rec.ensure_one()
            rec.state = 'draft'
            rec.approval_line_ids.unlink()

    def action_create_vendor_bill(self):

        for rec in self:
            
            if rec.vendor_bill_id:
                raise ValidationError(
                    "Vendor Bill already created."
                )

            if not rec.vendor_id:
                raise ValidationError(
                    "Vendor harus diisi terlebih dahulu."
                )
            
            selected_lines = rec.line_ids.filtered(lambda l: l.selected)
            
            if not selected_lines:
                raise ValidationError(
                    "Pilih minimal 1 product."
            )

            invoice_lines = []

            for line in selected_lines:
                invoice_lines.append((0, 0, {
                    'product_id': line.product_id.id,
                    'quantity': line.quantity,
                    'price_unit': line.price_unit,
                    'name': line.product_id.name,
                }))

            bill = self.env['account.move'].create({
                'move_type': 'in_invoice',
                'partner_id': rec.vendor_id.id,
                'invoice_line_ids': invoice_lines,
            })

            rec.vendor_bill_id = bill.id

            selected_lines.write({
                'selected': False
            })

            return {
                'type': 'ir.actions.act_window',
                'res_model': 'account.move',
                'res_id': bill.id,
                'view_mode': 'form',
            }