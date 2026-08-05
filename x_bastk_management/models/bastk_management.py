import logging
from datetime import timedelta

from odoo import models, fields, api, Command
from odoo.exceptions import UserError, ValidationError
from odoo.tools.misc import format_date

_logger = logging.getLogger(__name__)

BASTK_NOTIFICATION_SCOPE = 'bastk'

_DEFAULT_BASTK_END_REMINDERS = (
    ('D60', 'H-60 hari', lambda end, today: end - timedelta(days=60) == today),
    ('D30', 'H-30 hari', lambda end, today: end - timedelta(days=30) == today),
    ('D14', 'H-14 hari', lambda end, today: end - timedelta(days=14) == today),
    ('D7', 'H-7 hari', lambda end, today: end - timedelta(days=7) == today),
)


class BastkManagement(models.Model):
    _name = 'bastk.management'
    _description = 'BASTK Management'
    _rec_name = 'name'

    name = fields.Char(string='BASTK Number', required=True, copy=False, default='New')

    bastk_type_id = fields.Many2one('bastk.type', required=True)
    start_date = fields.Date(string='Tanggal Keluar', required=True)
    end_date = fields.Date(string='Tanggal Masuk')
    is_from_so = fields.Boolean(
        compute='_compute_is_from_so',
        string='Is from SO',
        store=False,
    )
    sale_order_id = fields.Many2one(
        'sale.order',
        string='SO Reference',
        store=True,
    )

    @api.depends('sale_order_id')
    def _compute_is_from_so(self):
        for rec in self:
            rec.is_from_so = bool(rec.sale_order_id)

    notification_end_reminders_sent = fields.Char(
        string='End date reminders already sent',
        copy=False,
        help='Comma-separated reminder stage keys already sent (see Notification template «End-date reminders»). '
             'Reset when End Date changes.',
    )
    notification_send_reminder_label = fields.Char(
        string='Reminder label (email render)',
        copy=False,
        help='Set only while sending the BASTK email so mail template body can use '
             'simple QWeb paths like object.notification_send_reminder_label.',
    )
    email_display_start = fields.Char(
        compute='_compute_email_display_fields',
        string='Start date (email)',
    )
    email_display_end = fields.Char(
        compute='_compute_email_display_fields',
        string='End date (email)',
    )
    email_display_state = fields.Char(
        compute='_compute_email_display_fields',
        string='State (email)',
    )

    partner_id = fields.Many2one('res.partner', required=True)
    pic_keluar = fields.Char(string='PIC (Keluar)')
    pic_masuk = fields.Char(string='PIC (Masuk)')
    call_number_keluar = fields.Char(string='Call Number (Keluar)')
    call_number_masuk = fields.Char(string='Call Number (Masuk)')

    address_id = fields.Many2one('res.partner')
    address_text = fields.Text()
    driver_name = fields.Char()

    vehicle_id = fields.Many2one('fleet.vehicle', required=True)

    asset_number = fields.Char(string='Asset Number', compute='_compute_vehicle_info', store=True)
    license_plate = fields.Char(compute='_compute_vehicle_info', store=True)
    unit_type = fields.Many2one('fleet.vehicle.model', compute='_compute_vehicle_info', store=True)
    color = fields.Char(compute='_compute_vehicle_info', store=True)
    model_year = fields.Char(compute='_compute_vehicle_info', store=True)
    vin_number = fields.Char(compute='_compute_vehicle_info', store=True)
    engine_number = fields.Char(compute='_compute_vehicle_info', store=True)

    is_disposal = fields.Boolean(related='bastk_type_id.is_disposal', readonly=True)
    is_disabled_after_submitted_in = fields.Boolean(related='bastk_type_id.is_disabled_after_submitted_in', readonly=True)
    need_submit_out = fields.Boolean(related='bastk_type_id.need_submit_out', readonly=True)
    need_submit_in = fields.Boolean(related='bastk_type_id.need_submit_in', readonly=True)
    has_goods_issue = fields.Boolean(compute='_compute_has_goods', store=False)
    has_goods_receive = fields.Boolean(compute='_compute_has_goods', store=False)
    is_goods_issue_done = fields.Boolean(compute='_compute_has_goods', store=False)
    is_goods_receive_done = fields.Boolean(compute='_compute_has_goods', store=False)
    is_all_pickings_done = fields.Boolean(compute='_compute_has_goods', store=False)
    
    can_submit_out = fields.Boolean(compute='_compute_button_visibility')
    can_submit_in = fields.Boolean(compute='_compute_button_visibility')
    can_done = fields.Boolean(compute='_compute_button_visibility')

    last_odometer = fields.Float(string='Last Odometer', compute='_compute_last_odometer', store=False)
    odometer_out = fields.Float(string='Odometer Out')
    odometer_in = fields.Float(string='Odometer In')

    @api.depends('vehicle_id.odometer')
    def _compute_last_odometer(self):
        for rec in self:
            rec.last_odometer = rec.vehicle_id.odometer if rec.vehicle_id else 0.0

    @api.depends('picking_ids', 'picking_ids.picking_type_code', 'picking_ids.state')
    def _compute_has_goods(self):
        for rec in self:
            rec.has_goods_issue = any(p.picking_type_code == 'outgoing' for p in rec.picking_ids)
            rec.has_goods_receive = any(p.picking_type_code == 'incoming' for p in rec.picking_ids)
            
            rec.is_goods_issue_done = rec.has_goods_issue and all(p.state == 'done' for p in rec.picking_ids if p.picking_type_code == 'outgoing')
            rec.is_goods_receive_done = rec.has_goods_receive and all(p.state == 'done' for p in rec.picking_ids if p.picking_type_code == 'incoming')
            
            rec.is_all_pickings_done = len(rec.picking_ids) > 0 and all(p.state == 'done' for p in rec.picking_ids)

    @api.depends('state', 'is_disposal', 'is_disabled_after_submitted_in', 'need_submit_out', 'need_submit_in', 'is_goods_issue_done', 'is_goods_receive_done', 'has_goods_issue', 'has_goods_receive')
    def _compute_button_visibility(self):
        for rec in self:
            rec.can_submit_out = False
            rec.can_submit_in = False
            rec.can_done = False
            
            if rec.state == 'draft':
                if rec.need_submit_out:
                    rec.can_submit_out = True
                elif rec.need_submit_in:
                    rec.can_submit_in = True
                else:
                    rec.can_done = True
                    
            elif rec.state == 'submitted_outside':
                if rec.need_submit_in:
                    if rec.is_disposal or rec.is_disabled_after_submitted_in:
                        if not rec.has_goods_issue or rec.is_goods_issue_done:
                            rec.can_done = True
                    else:
                        if not rec.has_goods_issue or rec.is_goods_issue_done:
                            rec.can_submit_in = True
                else:
                    rec.can_done = True
                    
            elif rec.state == 'submitted_inside':
                if not rec.has_goods_receive or rec.is_goods_receive_done:
                    rec.can_done = True

    description = fields.Text()
    line_ids = fields.One2many('bastk.description', 'bastk_id')
    line_keluar_ids = fields.One2many(
        'bastk.description', 'bastk_id',
        domain=[('bastk_type', '=', 'keluar')],
    )
    line_masuk_ids = fields.One2many(
        'bastk.description', 'bastk_id',
        domain=[('bastk_type', '=', 'masuk')],
    )

    remarks_keluar = fields.Text(string='Remarks (Keluar)')
    remarks_masuk = fields.Text(string='Remarks (Masuk)')
    customer_sign_keluar = fields.Binary(string='Customer Sign (Keluar)')
    customer_sign_masuk = fields.Binary(string='Customer Sign (Masuk)')
    cakrawala_sign_keluar = fields.Binary(string='Cakrawala Sign (Keluar)')
    cakrawala_sign_masuk = fields.Binary(string='Cakrawala Sign (Masuk)')

    customer_name_keluar = fields.Char(string='Nama (Customer Keluar)')
    cakrawala_name_keluar = fields.Char(string='Nama (Cakrawala Keluar)')
    customer_name_masuk = fields.Char(string='Nama (Customer Masuk)')
    cakrawala_name_masuk = fields.Char(string='Nama (Cakrawala Masuk)')

    attachment_keluar_ids = fields.Many2many(
        'ir.attachment',
        'bastk_management_attachment_keluar_rel',
        'bastk_id',
        'attachment_id',
        string='Attachments (Keluar)',
    )
    attachment_masuk_ids = fields.Many2many(
        'ir.attachment',
        'bastk_management_attachment_masuk_rel',
        'bastk_id',
        'attachment_id',
        string='Attachments (Masuk)',
    )
    image_keluar_ids = fields.One2many(
        'bastk.management.image', 'bastk_id',
        string='Photos (Keluar)',
    )
    image_masuk_ids = fields.One2many(
        'bastk.management.image', 'bastk_masuk_id',
        string='Photos (Masuk)',
    )
    
    picking_ids = fields.One2many('stock.picking', 'bastk_id', string='Transfers')
    picking_count = fields.Integer(compute='_compute_picking_count', string='Transfer Count')

    @api.depends('picking_ids')
    def _compute_picking_count(self):
        for rec in self:
            rec.picking_count = len(rec.picking_ids)

    
    state = fields.Selection([
        ('draft', 'Draft'),
        ('submitted_outside', 'Submitted Out'),
        ('submitted_inside', 'Submitted In'),
        ('done', 'Done'),
    ], string='State', default='draft')

    def action_submit_outside(self):
        for rec in self:
            if rec.state == 'draft':
                if not self.env.context.get('skip_submit_wizard'):
                    return {
                        'name': 'Submit BASTK',
                        'type': 'ir.actions.act_window',
                        'res_model': 'bastk.submit.wizard',
                        'view_mode': 'form',
                        'target': 'new',
                        'context': {
                            'default_bastk_id': rec.id,
                            'default_submit_type': 'out',
                        },
                    }
                if not rec.pic_keluar or not rec.call_number_keluar or not rec.odometer_out:
                    raise ValidationError("PIC (Keluar), Call Number (Keluar), and Odometer Out harus diisi sebelum Submit Out.")
                rec.state = 'submitted_outside'
                if rec.bastk_type_id.out_state_id:
                    rec.vehicle_id.state_id = rec.bastk_type_id.out_state_id
                if rec.bastk_type_id.out_substate_id:
                    rec.vehicle_id.fleet_sub_status_id = rec.bastk_type_id.out_substate_id
                
                if rec.odometer_out:
                    self.env['fleet.vehicle.odometer'].create({
                        'vehicle_id': rec.vehicle_id.id,
                        'value': rec.odometer_out,
                        'date': rec.start_date,
                    })

    def action_submit_inside(self):
        for rec in self:
            if rec.state in ('draft', 'submitted_outside'):
                if not self.env.context.get('skip_submit_wizard'):
                    return {
                        'name': 'Submit BASTK',
                        'type': 'ir.actions.act_window',
                        'res_model': 'bastk.submit.wizard',
                        'view_mode': 'form',
                        'target': 'new',
                        'context': {
                            'default_bastk_id': rec.id,
                            'default_submit_type': 'in',
                        },
                    }
                if not rec.pic_masuk or not rec.call_number_masuk or not rec.odometer_in:
                    raise ValidationError("PIC (Masuk), Call Number (Masuk), and Odometer In harus diisi sebelum Submit In.")
                rec.state = 'submitted_inside'
                if rec.bastk_type_id.in_state_id:
                    rec.vehicle_id.state_id = rec.bastk_type_id.in_state_id
                if rec.bastk_type_id.in_substate_id:
                    rec.vehicle_id.fleet_sub_status_id = rec.bastk_type_id.in_substate_id
                
                if rec.odometer_in:
                    self.env['fleet.vehicle.odometer'].create({
                        'vehicle_id': rec.vehicle_id.id,
                        'value': rec.odometer_in,
                        'date': rec.end_date,
                    })

    def action_done(self):
        for rec in self:
            if rec.state in ('draft', 'submitted_inside', 'submitted_outside'):
                rec.state = 'done'
                if (rec.is_disposal or rec.is_disabled_after_submitted_in) and rec.vehicle_id:
                    inactive_state = self.env['fleet.vehicle.state'].search([('is_inactive_state', '=', True)], limit=1)
                    if inactive_state:
                        rec.vehicle_id.state_id = inactive_state.id
                    else:
                        raise UserError("Belum ada state yang di-set sebagai Inactive State di konfigurasi Vehicle State!")

    def action_reset_to_draft(self):
        for rec in self:
            if rec.state == 'done':
                raise UserError(
                    "Dokumen yang sudah berstatus Done tidak dapat dikembalikan ke Draft."
                )
            rec.state = 'draft'

    def action_open_wizard_goods_issue(self):
        self.ensure_one()
        return {
            'name': 'Create Goods Issue',
            'type': 'ir.actions.act_window',
            'res_model': 'bastk.picking.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_bastk_id': self.id,
                'default_picking_type_code': 'outgoing',
            }
        }

    def action_open_wizard_goods_receive(self):
        self.ensure_one()
        return {
            'name': 'Create Goods Receive',
            'type': 'ir.actions.act_window',
            'res_model': 'bastk.picking.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_bastk_id': self.id,
                'default_picking_type_code': 'incoming',
            }
        }

    def action_view_pickings(self):
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id("stock.action_picking_tree_all")
        pickings = self.picking_ids
        if len(pickings) > 1:
            action['domain'] = [('id', 'in', pickings.ids)]
        elif pickings:
            form_view = [(self.env.ref('stock.view_picking_form').id, 'form')]
            if 'views' in action:
                action['views'] = form_view + [(state,view) for state,view in action['views'] if view != 'form']
            else:
                action['views'] = form_view
            action['res_id'] = pickings.id
        context = dict(self.env.context)
        context.update({
            'default_bastk_id': self.id,
        })
        action['context'] = context
        return action


    def write(self, vals):
        if 'sale_order_id' in vals and 'so_reference' not in vals:
            sale_order = self.env['sale.order'].browse(vals['sale_order_id']) if vals['sale_order_id'] else False
            vals['so_reference'] = sale_order.name if sale_order else False
        if 'end_date' in vals:
            vals = dict(vals)
            vals['notification_end_reminders_sent'] = False
            vals['notification_send_reminder_label'] = False
        return super().write(vals)

    @api.depends('start_date', 'end_date', 'state')
    def _compute_email_display_fields(self):
        state_labels = dict(self._fields['state'].selection)
        for rec in self:
            rec.email_display_start = (
                format_date(rec.env, rec.start_date) if rec.start_date else ''
            )
            rec.email_display_end = (
                format_date(rec.env, rec.end_date) if rec.end_date else ''
            )
            rec.email_display_state = state_labels.get(rec.state, rec.state or '') or ''

    @api.model
    def _bastk_active_reminder_schedule(self):
        """Use reminder lines on the active “Use for = BASTK” template, else built-in default."""
        Notif = self.env['x.notification.template'].sudo()
        template = Notif.get_template_for_scope_model(
            BASTK_NOTIFICATION_SCOPE,
            'bastk.management',
        )
        if template and template.reminder_line_ids:
            return template.iter_end_date_reminder_checks()
        return list(_DEFAULT_BASTK_END_REMINDERS)

    def _bastk_end_reminder_stages_sent(self):
        self.ensure_one()
        if not self.notification_end_reminders_sent:
            return set()
        return {
            x.strip()
            for x in self.notification_end_reminders_sent.split(',')
            if x.strip()
        }

    def _bastk_send_end_notify(self, stage_key, stage_label):
        self.ensure_one()
        template_context = {
            'bastk_reminder_stage': stage_key,
            'bastk_reminder_label': stage_label,
        }
        self.write({'notification_send_reminder_label': stage_label})
        try:
            self.env['x.notification.template'].sudo().send_notification_for_scope(
                self,
                BASTK_NOTIFICATION_SCOPE,
                template_context=template_context,
            )
            return True
        except UserError as err:
            _logger.warning(
                'BASTK end-date reminder skipped (record %s, stage %s): %s',
                self.id, stage_key, err,
            )
            return False
        finally:
            self.write({'notification_send_reminder_label': False})

    @api.model
    def cron_send_end_date_notifications(self):
        """Daily: BASTK end-date emails via Notification template «Use for = BASTK»."""
        reminders = self._bastk_active_reminder_schedule()
        today = fields.Date.today()
        candidates = self.search([
            ('end_date', '!=', False),
            ('state', 'in', ('submitted_inside', 'submitted_outside')),
        ])
        for rec in candidates:
            end = rec.end_date
            if end < today:
                continue
            sent = rec._bastk_end_reminder_stages_sent()
            new_stages = []
            for stage_key, stage_label, predicate in reminders:
                if stage_key in sent:
                    continue
                if not predicate(end, today):
                    continue
                if rec._bastk_send_end_notify(stage_key, stage_label):
                    new_stages.append(stage_key)
            if new_stages:
                rec.notification_end_reminders_sent = ','.join(
                    sorted(sent | set(new_stages))
                )

    def _build_checklist_lines(self):
        """Buat line dari master description, pisahkan per keluar/masuk."""
        masters = self.env['bastk.master.description'].search([])
        keluar_lines = []
        masuk_lines = []
        for item in masters:
            if item.type in ('keluar', 'both'):
                keluar_lines.append(Command.create({
                    'checklist_id': item.id,
                    'bastk_type': 'keluar',
                }))
            if item.type in ('masuk', 'both'):
                masuk_lines.append(Command.create({
                    'checklist_id': item.id,
                    'bastk_type': 'masuk',
                }))
        return keluar_lines, masuk_lines

    def _next_bastk_name(self):
        """Get next BASTK sequence with safe fallbacks."""
        seq_model = self.env['ir.sequence'].sudo()
        seq_val = seq_model.next_by_code('bastk.record')
        if seq_val:
            return seq_val

        sequence = seq_model.search([
            ('code', '=', 'bastk.record'),
            '|',
            ('company_id', '=', self.env.company.id),
            ('company_id', '=', False),
        ], order='company_id desc, id asc', limit=1)
        if sequence:
            return seq_model.next_by_id(sequence.id)

        return 'New'

    @api.model
    def default_get(self, field_list):
        values = super().default_get(field_list)
        keluar_lines, masuk_lines = self._build_checklist_lines()
        if not values.get('line_keluar_ids'):
            values['line_keluar_ids'] = keluar_lines
        if not values.get('line_masuk_ids'):
            values['line_masuk_ids'] = masuk_lines
        return values

    @api.depends(
        'vehicle_id',
        'vehicle_id.fleet_document_license_plate',
        'vehicle_id.fleet_document_vin_number',
        'vehicle_id.fleet_document_asset_number',
        'vehicle_id.license_plate',
        'vehicle_id.vin_sn',
        'vehicle_id.asset_number',
        'vehicle_id.model_id',
        'vehicle_id.color',
        'vehicle_id.model_year',
        'vehicle_id.engine_number',
    )
    def _compute_vehicle_info(self):
        for rec in self:
            if rec.vehicle_id:
                v = rec.vehicle_id
                rec.asset_number = v.fleet_document_asset_number or ''
                rec.license_plate = v.fleet_document_license_plate or ''
                rec.unit_type = v.model_id
                rec.color = v.color
                rec.model_year = v.model_year
                rec.vin_number = v.fleet_document_vin_number or ''
                rec.engine_number = v.engine_number
            else:
                rec.asset_number = False
                rec.license_plate = False
                rec.unit_type = False
                rec.color = False
                rec.model_year = False
                rec.vin_number = False
                rec.engine_number = False

    @api.onchange('vehicle_id')
    def _onchange_vehicle_id_photos(self):
        for rec in self:
            rec.image_keluar_ids = [(5, 0, 0)]
            rec.image_masuk_ids = [(5, 0, 0)]
            if rec.vehicle_id:
                category = rec.vehicle_id.category_id or (rec.vehicle_id.model_id and rec.vehicle_id.model_id.category_id)
                if category:
                    photos_keluar = []
                    photos_masuk = []
                    for photo in category.photo_ids:
                        photos_keluar.append((0, 0, {
                            'name': photo.name,
                            'image': photo.image,
                        }))
                        photos_masuk.append((0, 0, {
                            'name': photo.name,
                            'image': photo.image,
                        }))
                    rec.image_keluar_ids = photos_keluar
                    rec.image_masuk_ids = photos_masuk
                
                rec.odometer_out = rec.last_odometer
                rec.odometer_in = rec.last_odometer


    @api.onchange('partner_id')
    def _onchange_partner_id_set_address(self):
        for rec in self:
            if not rec.partner_id:
                rec.address_id = False
                rec.address_text = False
                continue

            partner = rec.partner_id
            rec.address_id = partner
            candidate_partners = partner | partner.parent_id | partner.commercial_partner_id

            if partner.user_ids:
                candidate_partners |= partner.user_ids.mapped('partner_id')

            address = False
            for partner_candidate in candidate_partners:
                formatted_address = partner_candidate._display_address(without_company=True).strip()
                if formatted_address:
                    address = formatted_address
                    break
            rec.address_text = address

    @api.model_create_multi
    def create(self, vals_list):
        requires_id_fallback = []
        for vals in vals_list:
            use_id_fallback = False
            if vals.get('name', 'New') == 'New':
                generated_name = self._next_bastk_name()
                if generated_name == 'New':
                    use_id_fallback = True
                vals['name'] = generated_name
            if not vals.get('line_ids') and not vals.get('line_keluar_ids') and not vals.get('line_masuk_ids'):
                keluar_lines, masuk_lines = self._build_checklist_lines()
                vals['line_ids'] = keluar_lines + masuk_lines
            requires_id_fallback.append(use_id_fallback)

        records = super().create(vals_list)
        for rec, use_id_fallback in zip(records, requires_id_fallback):
            if use_id_fallback:
                rec.name = f"BASTK/{rec.create_date.month:02d}/{rec.create_date.year}/{rec.id}"
        return records

class BastkManagementImage(models.Model):
    _name = 'bastk.management.image'
    _description = 'BASTK Management Image'

    name = fields.Char(string='Name', required=True)
    bastk_id = fields.Many2one('bastk.management', string='BASTK (Keluar)', ondelete='cascade')
    bastk_masuk_id = fields.Many2one('bastk.management', string='BASTK (Masuk)', ondelete='cascade')
    image = fields.Image(string='Image', max_width=1920, max_height=1920)
    annotated_image = fields.Image(string='Annotated Image', max_width=1920, max_height=1920)
