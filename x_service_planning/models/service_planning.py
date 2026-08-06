import logging
from dateutil.relativedelta import relativedelta

from odoo import models, fields, api
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)

SERVICE_PLANNING_NOTIFICATION_SCOPE = 'service_planning_km'


class MasterServicePlanning(models.Model):
    _name = 'master.service.planning'
    _description = 'Master Service Planning'

    name = fields.Char(string="Name", required=True)


class ServicePlanning(models.Model):
    _name = 'service.planning'
    _description = 'Service Planning'
    _rec_name = 'name'
    _order = 'id desc'

    name = fields.Char(string="Name", readonly=True, default='/')
    vehicle_id = fields.Many2one('fleet.vehicle', string="Vehicle", required=True)
    need_replacement = fields.Boolean(string="Need Replacement Car")
    sequence = fields.Integer(string="Sequence", default=10)

    state = fields.Selection([
        ('active', 'Active'),
        ('done', 'Done'),
        ('cancelled', 'Cancelled'),
    ], string="Status", default='active', required=True, copy=False)

    license_plate = fields.Char(
        related='vehicle_id.fleet_document_license_plate',
        string='License Plate',
        store=True,
        readonly=True,
    )
    vin_number = fields.Char(
        related='vehicle_id.fleet_document_vin_number',
        string='VIN Number',
        store=True,
        readonly=True,
    )
    engine_number = fields.Char(
        related='vehicle_id.engine_number',
        string='Engine Number',
        store=True,
        readonly=True,
    )
    asset_number = fields.Char(
        related='vehicle_id.fleet_document_asset_number',
        string='Asset Number',
        store=True,
        readonly=True,
    )
    model_year = fields.Selection(
        related='vehicle_id.model_year',
        string='Year',
        store=True,
        readonly=True,
    )

    line_ids = fields.One2many('service.planning.line', 'planning_id', string="Service Parts")

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('vehicle_id') and not vals.get('name'):
                vehicle = self.env['fleet.vehicle'].browse(vals['vehicle_id'])
                vals['name'] = f"Service Planning - {vehicle.name}"
        return super().create(vals_list)

    @api.onchange('vehicle_id')
    def _onchange_vehicle(self):
        for rec in self:
            if rec.vehicle_id:
                rec.name = f"Service Planning - {rec.vehicle_id.name}"
            else:
                rec.name = '/'

    def action_set_done(self):
        """Mark planning as Done. Resets all reminder flags on lines."""
        for rec in self:
            rec.state = 'done'
            rec.line_ids.write({
                'reminder_sent': False,
                'reminder_sent_date': False,
            })

    def action_set_cancelled(self):
        """Cancel the planning."""
        self.write({'state': 'cancelled'})

    def action_set_active(self):
        """Reactivate a Done or Cancelled planning."""
        self.write({'state': 'active'})

    def action_create_spk(self):
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Info',
                'message': 'SPK akan dibuat di tahap integrasi',
                'type': 'success',
            }
        }

    def action_create_replacement(self):
        self.ensure_one()
        vehicle = self.vehicle_id
        company = vehicle.company_id or self.env.company
        pic = vehicle.driver_id.name if vehicle.driver_id else '/'

        existing = self.env['replacement.car'].search([
            ('service_planning_id', '=', self.id),
            ('state', '!=', 'cancel'),
        ], limit=1)

        if existing:
            return {
                'type': 'ir.actions.act_window',
                'name': 'Replacement Car',
                'res_model': 'replacement.car',
                'view_mode': 'form',
                'res_id': existing.id,
                'target': 'current',
            }

        replacement = self.env['replacement.car'].create({
            'company_id': company.id,
            'vehicle_old_id': vehicle.id,
            'service_planning_id': self.id,
            'request_date': fields.Date.context_today(self),
            'pic_name': pic,
            'estimation_use_date': fields.Date.context_today(self),
            'reason': '',
        })

        return {
            'type': 'ir.actions.act_window',
            'name': 'Replacement Car',
            'res_model': 'replacement.car',
            'view_mode': 'form',
            'res_id': replacement.id,
            'target': 'current',
        }

    # ─────────────────────────────────────────────────────────────────────
    # Cron: Odometer & Interval Reminder
    # ─────────────────────────────────────────────────────────────────────

    @api.model
    def cron_send_odometer_reminders(self):
        """Daily cron: sends service reminder emails based on odometer buffer and/or interval months.

        Logic:
        - Only processes 'active' service.planning records.
        - For each line, evaluates TWO conditions (either is sufficient to trigger reminder):
            1. Odometer: current vehicle odometer >= buffer_km (if buffer_km is set)
            2. Interval: last_service_date + interval months <= today (if last_service_date is set)
        - Reminder is sent every day the condition is still met (repeating), until state = done.
        - Email goes to Fleet Manager of the vehicle, or test email if test_mode=1.
        """
        params = self.env['ir.config_parameter'].sudo()
        test_mode = params.get_param('service_planning.reminder.test_mode', '1') == '1'
        test_email = params.get_param('service_planning.reminder.test_email', '')

        today = fields.Date.today()

        active_plannings = self.search([('state', '=', 'active')])
        if not active_plannings:
            return

        # Batch-load max odometer for all vehicles involved
        vehicle_ids = active_plannings.mapped('vehicle_id').ids
        odometer_data = {}
        if vehicle_ids:
            odometer_records = self.env['fleet.vehicle.odometer'].read_group(
                [('vehicle_id', 'in', vehicle_ids)],
                ['vehicle_id', 'value:max'],
                ['vehicle_id'],
            )
            for row in odometer_records:
                odometer_data[row['vehicle_id'][0]] = row['value']

        for planning in active_plannings:
            vehicle = planning.vehicle_id
            current_odometer = odometer_data.get(vehicle.id, 0.0)

            # Resolve Fleet Manager recipient
            email_values = self._resolve_email_values(vehicle, test_mode, test_email)
            if not email_values:
                _logger.warning(
                    'Service Planning %s (id=%s): no valid recipient found, skipping.',
                    planning.name, planning.id,
                )
                continue

            for line in planning.line_ids:
                should_remind = False
                reasons = []

                # -- Condition 1: Odometer buffer check --
                if line.buffer_km:
                    try:
                        buffer_val = int(line.buffer_km)
                    except (TypeError, ValueError):
                        buffer_val = 0
                    if buffer_val > 0 and current_odometer >= buffer_val:
                        should_remind = True
                        try:
                            km_target = int(line.kilometer or 0)
                        except (TypeError, ValueError):
                            km_target = 0
                        reasons.append(
                            f"Odometer saat ini ({int(current_odometer):,} km) "
                            f"telah mencapai buffer reminder ({buffer_val:,} km / "
                            f"target {km_target:,} km)"
                        )

                # -- Condition 2: Interval month check --
                if line.last_service_date and line.interval > 0:
                    next_service_date = line.last_service_date + relativedelta(months=line.interval)
                    if today >= next_service_date:
                        should_remind = True
                        reasons.append(
                            f"Interval service {line.interval} bulan telah tercapai "
                            f"(tanggal service berikutnya: {next_service_date.strftime('%d/%m/%Y')})"
                        )

                if not should_remind:
                    continue

                # Send reminder
                sent = self._send_service_planning_reminder(
                    planning, line, vehicle, reasons, email_values
                )
                if sent:
                    line.write({
                        'reminder_sent': True,
                        'reminder_sent_date': fields.Datetime.now(),
                    })
                    _logger.info(
                        'Service Planning %s line %s: reminder sent. Reasons: %s',
                        planning.name, line.id, '; '.join(reasons),
                    )

    @api.model
    def _resolve_email_values(self, vehicle, test_mode, test_email):
        """Resolve the email recipient for the reminder.

        Priority: Fleet Manager > Driver.
        In test_mode, always redirect to test_email.
        Returns dict with 'email_to' and 'recipient_ids', or None if no valid recipient.
        """
        if test_mode:
            if not test_email:
                _logger.warning(
                    'test_mode=1 but service_planning.reminder.test_email is empty. '
                    'No email will be sent.'
                )
                return None
            return {'email_to': test_email, 'recipient_ids': []}

        # Production: Fleet Manager first, then Driver
        partner = None
        if hasattr(vehicle, 'manager_id') and vehicle.manager_id:
            partner = vehicle.manager_id
        elif vehicle.driver_id:
            partner = vehicle.driver_id

        if not partner or not partner.email:
            return None

        return {
            'email_to': partner.email_formatted,
            'recipient_ids': [(6, 0, [partner.id])],
        }

    @api.model
    def _send_service_planning_reminder(self, planning, line, vehicle, reasons, email_values):
        """Send the reminder email via x.notification.template infrastructure."""
        try:
            self.env['x.notification.template'].sudo().send_notification_for_scope(
                planning,
                SERVICE_PLANNING_NOTIFICATION_SCOPE,
                template_context={
                    'reminder_reasons': reasons,
                    'reminder_line': line,
                    'current_vehicle': vehicle,
                },
                email_values=email_values,
            )
            return True
        except Exception as err:
            _logger.warning(
                'Service Planning reminder failed for planning %s (id=%s), line %s: %s',
                planning.name, planning.id, line.id, err,
            )
            return False


class ServicePlanningLine(models.Model):
    _name = 'service.planning.line'
    _description = 'Service Planning Line'
    _order = 'sequence, id'

    planning_id = fields.Many2one('service.planning', string="Service Planning", required=True, ondelete='cascade')
    sequence = fields.Integer(string="Sequence", default=10)

    service_planning_id = fields.Many2one(
        'master.service.planning',
        string="Service Planning",
        required=True
    )
    kilometer = fields.Char(
        string="Kilometer (Target)",
        required=True,
        help="Target odometer untuk jadwal service (km)."
    )
    buffer_km = fields.Char(
        string="Buffer (km)",
        help="Reminder mulai dikirim saat odometer kendaraan mencapai nilai ini.\n"
             "Harus lebih kecil dari Target Kilometer.\n"
             "Contoh: Target 10.000 km, Buffer 8.000 km → email dikirim saat odometer >= 8.000 km."
    )
    interval = fields.Integer(
        string="Interval (Month)",
        required=True,
        help="Interval waktu service dalam bulan."
    )
    last_service_date = fields.Date(
        string="Tanggal Service Terakhir",
        help="Isi tanggal service terakhir dilakukan. "
             "Digunakan untuk menghitung kapan service berikutnya berdasarkan interval bulan."
    )
    brand_recommendation = fields.Char()
    remarks = fields.Text()

    # Reminder tracking
    reminder_sent = fields.Boolean(
        string="Reminder Aktif",
        default=False,
        copy=False,
        help="True jika reminder sedang aktif dikirim (kondisi terpenuhi). "
             "Direset otomatis jika Kilometer target atau Buffer berubah, "
             "atau saat header planning di-set kembali ke Active setelah Done."
    )
    reminder_sent_date = fields.Datetime(
        string="Terakhir Dikirim",
        copy=False,
        readonly=True,
        help="Tanggal dan waktu terakhir kali reminder berhasil dikirim."
    )

    def write(self, vals):
        """Auto-reset reminder flags when kilometer target or buffer_km changes."""
        reset_fields = {'kilometer', 'buffer_km'}
        if reset_fields & set(vals.keys()):
            vals.setdefault('reminder_sent', False)
            vals.setdefault('reminder_sent_date', False)
        return super().write(vals)

    @api.constrains('kilometer', 'interval')
    def _check_values(self):
        for rec in self:
            try:
                km_value = int(rec.kilometer or 0)
            except (TypeError, ValueError):
                raise ValidationError("Kilometer harus berupa angka bulat")
            if km_value <= 0:
                raise ValidationError("Kilometer harus lebih dari 0")
            if rec.interval <= 0:
                raise ValidationError("Interval harus lebih dari 0")

    @api.constrains('buffer_km', 'kilometer')
    def _check_buffer_km(self):
        for rec in self:
            if not rec.buffer_km:
                continue
            try:
                buffer_val = int(rec.buffer_km)
                km_val = int(rec.kilometer or 0)
            except (TypeError, ValueError):
                raise ValidationError("Buffer Kilometer harus berupa angka bulat.")
            if buffer_val <= 0:
                raise ValidationError("Buffer Kilometer harus lebih dari 0.")
            if buffer_val >= km_val:
                raise ValidationError(
                    f"Buffer ({buffer_val:,} km) harus lebih kecil dari Target Kilometer ({km_val:,} km)."
                )

    @api.constrains('planning_id', 'service_planning_id', 'kilometer')
    def _check_unique_line(self):
        for rec in self:
            existing = self.search([
                ('planning_id', '=', rec.planning_id.id),
                ('service_planning_id', '=', rec.service_planning_id.id),
                ('kilometer', '=', str(rec.kilometer)),
                ('id', '!=', rec.id)
            ])
            if existing:
                raise ValidationError("Service Planning dengan kilometer yang sama sudah ada di perencanaan ini!")