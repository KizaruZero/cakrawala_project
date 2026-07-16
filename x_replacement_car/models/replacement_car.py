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

    customer_id = fields.Many2one(
        'res.partner',
        string="Company Client",
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

    spk_reference_id = fields.Many2one(
        'fleet.spk',
        string="SPK Number",
        compute='_compute_spk_reference_id',
        help="The SPK this replacement car was requested from.",
    )

    @api.depends('spk_ids')
    def _compute_spk_reference_id(self):
        """Single-record view of spk_ids, so the form can show it as a link.

        A replacement car is always created from exactly one SPK; spk_ids stays
        many2many because the report and the SPK-side lookup rely on it.
        """
        for rec in self:
            rec.spk_reference_id = rec.spk_ids[:1]

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

    new_company_client_id = fields.Many2one('res.partner', related='vehicle_new_id.driver_id', string="New Company Client", readonly=True)
    new_license_plate = fields.Char(related='vehicle_new_id.fleet_document_license_plate', string="New License Plate")
    new_vehicle_model_id = fields.Many2one('fleet.vehicle.model', related='vehicle_new_id.model_id', string="New Vehicle Model")
    new_year = fields.Selection(related='vehicle_new_id.model_year', string="New Year")
    new_color = fields.Char(related='vehicle_new_id.color', string="New Color")

    
    approval_line_ids = fields.One2many(
        'replacement.approval',
        'replacement_car_id',
        string="Approval Lines"
    )
    
    bastk_ids = fields.One2many(
        'bastk.management',
        'replacement_car_id',
        string="BASTK",
        readonly=True,
    )

    bastk_count = fields.Integer(
        string="BASTK Count",
        compute="_compute_bastk_count",
    )

    @api.depends('bastk_ids')
    def _compute_bastk_count(self):
        for rec in self:
            rec.bastk_count = len(rec.bastk_ids)

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

    def action_done(self):
        for rec in self:
            if not rec.bastk_ids:
                raise ValidationError(_(
                    "You cannot complete this Replacement Car because no BASTK record has been created for it yet. "
                    "Please create a BASTK first."
                ))
            # Check if at least one BASTK is submitted_outside or further
            valid_bastks = rec.bastk_ids.filtered(lambda b: b.state in ('submitted_outside', 'submitted_inside', 'done'))
            if not valid_bastks:
                raise ValidationError(_(
                    "You cannot complete this Replacement Car because the associated BASTK is not yet 'Submitted Out'. "
                    "Please submit the BASTK first."
                ))
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
            
    def action_create_bastk(self):
        """Buka form BASTK baru dengan vehicle dan customer dari RC ini."""
        self.ensure_one()
        if self.bastk_ids:
            # Satu Replacement Car hanya boleh punya satu BASTK. Tombol Create
            # sudah disembunyikan begitu BASTK ada, tapi klik dari tab lama yang
            # belum ter-refresh harus mengarah ke BASTK yang sudah ada, bukan
            # membuka form kosong kedua.
            return self.action_view_bastk()
        ctx = {
            'default_replacement_car_id': self.id,
        }
        if self.vehicle_new_id:
            ctx['default_vehicle_id'] = self.vehicle_new_id.id
        if self.customer_id:
            ctx['default_partner_id'] = self.customer_id.id
        return {
            'name': _('Create BASTK'),
            'type': 'ir.actions.act_window',
            'res_model': 'bastk.management',
            'view_mode': 'form',
            'target': 'current',
            'context': ctx,
        }

    def action_view_bastk(self):
        """Tampilkan daftar / detail BASTK yang berasal dari RC ini."""
        self.ensure_one()
        action = self.env['ir.actions.actions']._for_xml_id(
            'x_bastk_management.action_bastk'
        )
        if self.bastk_count == 1:
            action['views'] = [(False, 'form')]
            action['res_id'] = self.bastk_ids.id
        else:
            action['domain'] = [('replacement_car_id', '=', self.id)]
        return action
    
    # def action_create_good_issue(self):
    #     """Trigger Goods Issue (Delivery Order) untuk kendaraan pengganti.

    #     Produk yang dikeluarkan adalah vehicle_new_id.product_id —
    #     produk Storable yang merepresentasikan unit kendaraan pengganti.
    #     Serial Number diisi oleh petugas saat validasi DO di Inventory.
    #     """
    #     for rec in self:
    #         if rec.good_issue_id and rec.good_issue_id.state != 'cancel':
    #             raise ValidationError(
    #                 "Good Issue untuk dokumen ini sudah pernah dibuat (%s)."
    #                 % rec.good_issue_id.name
    #             )

    #         picking_type = rec.goods_issue_source_id
    #         if not picking_type:
    #             raise ValidationError(
    #                 "Goods Issue Source wajib diisi sebelum membuat Good Issue."
    #             )
    #         if picking_type.code != 'outgoing':
    #             raise ValidationError(
    #                 "Goods Issue Source harus bertipe Delivery."
    #             )

    #         if not rec.vehicle_new_id:
    #             raise ValidationError(
    #                 "Kendaraan pengganti (Replacement Vehicle) wajib diisi "
    #                 "sebelum membuat Good Issue."
    #             )

    #         new_vehicle = rec.vehicle_new_id
    #         old_vehicle = rec.vehicle_old_id
    #         lot = False
    #         product = False
    #         asset_number = new_vehicle.asset_number
    #         if asset_number:
    #             lot = self.env['stock.lot'].search([
    #                 ('name', '=', asset_number),
    #                 ('company_id', '=', self.env.company.id),
    #             ], limit=1)
    #             if lot:
    #                 product = lot.product_id

    #         if not product:
    #             product = new_vehicle.product_id

    #         if not product:
    #             raise ValidationError(
    #                 "Kendaraan pengganti '%s' belum memiliki Produk (Product) yang terkait.\n\n"
    #                 "Pastikan field 'Product' sudah terisi di data kendaraan tersebut."
    #                 % new_vehicle.display_name
    #             )

    #         new_model = new_vehicle.model_id.display_name if new_vehicle.model_id else new_vehicle.display_name
    #         new_plate = new_vehicle.license_plate or ''
    #         rc_ref = rec.name or ''
    #         rc_notes = rec.reason or ''

    #         desc_parts = []
    #         if new_model:
    #             desc_parts.append(_("Replacement Vehicle: %s") % new_model)
    #         if new_plate and str(new_plate).strip().lower() != 'false':
    #             desc_parts.append(_("License Plate: %s") % new_plate)
    #         if rc_ref:
    #             desc_parts.append(_("Source RC: %s") % rc_ref)
    #         if rc_notes and str(rc_notes).strip().lower() != 'false':
    #             desc_parts.append(_("Notes: %s") % rc_notes)
    #         picking_description = "\n".join(desc_parts)

    #         analytic_acc = new_vehicle.analytic_account_id
    #         rc_analytic_distribution = {str(analytic_acc.id): 100} if analytic_acc else {}

    #         move_vals = {
    #             'product_id': product.id,
    #             'product_uom_qty': 1.0,
    #             'product_uom': product.uom_id.id,
    #             'location_id': picking_type.default_location_src_id.id,
    #             'location_dest_id': picking_type.default_location_dest_id.id,
    #             'description_picking': picking_description,
    #         }
    #         if rc_analytic_distribution:
    #             move_vals['x_spk_analytic_distribution'] = rc_analytic_distribution

    #         picking = self.env['stock.picking'].create({
    #             'picking_type_id': picking_type.id,
    #             'origin': rec.name,
    #             'location_id': picking_type.default_location_src_id.id,
    #             'location_dest_id': picking_type.default_location_dest_id.id,
    #             'move_ids': [(0, 0, move_vals)],
    #         })

    #         picking.action_confirm()
    #         picking.action_assign()

    #         if lot and lot.product_id == product:
    #             move_line_vals = {'lot_id': lot.id}
    #             if hasattr(lot, 'initial_license_plate'):
    #                 move_line_vals['initial_license_plate'] = lot.initial_license_plate or new_vehicle.initial_license_plate or ''
    #             if hasattr(lot, 'chassis_number'):
    #                 move_line_vals['chassis_number'] = lot.chassis_number or getattr(new_vehicle, 'chassis_number', '') or ''
    #             if hasattr(lot, 'engine_number'):
    #                 move_line_vals['engine_number'] = lot.engine_number or getattr(new_vehicle, 'engine_number', '') or ''
    #             if hasattr(lot, 'vehicle_year_id') and lot.vehicle_year_id:
    #                 move_line_vals['vehicle_year_id'] = lot.vehicle_year_id.id
    #             if hasattr(lot, 'vehicle_color_id') and lot.vehicle_color_id:
    #                 move_line_vals['vehicle_color_id'] = lot.vehicle_color_id.id
    #             picking.move_line_ids.write(move_line_vals)
    #         rec.good_issue_id = picking.id

    def action_reset_to_draft(self):
        for rec in self:
            rec.ensure_one()
            rec.state = 'draft'
            rec.approval_line_ids.unlink()