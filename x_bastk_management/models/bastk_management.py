from odoo import models, fields, api, Command


class BastkManagement(models.Model):
    _name = 'bastk.management'
    _description = 'BASTK Management'
    _rec_name = 'name'

    name = fields.Char(string='BASTK Number', required=True, copy=False, default='New')

    bastk_type_id = fields.Many2one('bastk.type', required=True)
    start_date = fields.Date(required=True)
    end_date = fields.Date(required=True)

    partner_id = fields.Many2one('res.partner', required=True)
    pic_partner = fields.Char()
    call_number = fields.Integer()

    address_id = fields.Many2one('res.partner')
    driver_name = fields.Char()

    vehicle_id = fields.Many2one('fleet.vehicle', required=True)

    asset_number = fields.Many2one('fleet.vehicle', compute='_compute_vehicle_info', store=True)
    license_plate = fields.Char(compute='_compute_vehicle_info', store=True)
    unit_type = fields.Many2one('fleet.vehicle.model', compute='_compute_vehicle_info', store=True)
    color = fields.Char(compute='_compute_vehicle_info', store=True)
    model_year = fields.Char(compute='_compute_vehicle_info', store=True)
    vin_number = fields.Char(compute='_compute_vehicle_info', store=True)
    engine_number = fields.Char(compute='_compute_vehicle_info', store=True)

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

    remarks = fields.Text()
    customer_sign = fields.Binary()
    cakrawala_sign = fields.Binary()

    attachment_ids = fields.Many2many('ir.attachment')

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

        # Fallback: locate sequence manually (company-specific first, then global)
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

    @api.depends('vehicle_id')
    def _compute_vehicle_info(self):
        for rec in self:
            if rec.vehicle_id:
                rec.asset_number = rec.vehicle_id.id
                rec.license_plate = rec.vehicle_id.license_plate
                rec.unit_type = rec.vehicle_id.model_id
                rec.color = rec.vehicle_id.color
                rec.model_year = rec.vehicle_id.model_year
                rec.vin_number = rec.vehicle_id.vin_sn
                rec.engine_number = rec.vehicle_id.engine_number

    @api.onchange('partner_id')
    def _onchange_partner_id_set_address(self):
        for rec in self:
            rec.address_id = rec.partner_id

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
