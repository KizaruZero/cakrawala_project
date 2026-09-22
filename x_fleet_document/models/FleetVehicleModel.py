from dateutil.relativedelta import relativedelta
from odoo import _, fields, models, api
from odoo.exceptions import ValidationError, UserError


class FleetVehicle(models.Model):
    _inherit = 'fleet.vehicle'

    license_plate_history_ids = fields.One2many(
        'fleet.vehicle.license.plate.history',
        'vehicle_id',
        string='License Plate History',
        readonly=True,
    )

    sub_type_id = fields.Many2one(
        'fleet.vehicle.sub.type',
        string='Sub Type',
        tracking=True,
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('license_plate') and vals.get('initial_license_plate'):
                vals['license_plate'] = vals['initial_license_plate']
        records = super().create(vals_list)
        History = self.env['fleet.vehicle.license.plate.history']
        for record in records:
            if record.license_plate:
                History.create({
                    'vehicle_id': record.id,
                    'license_plate': record.license_plate,
                    'valid_from': None,
                    'valid_until': None,
                })
        return records

    def write(self, vals):
        if 'license_plate' in vals:
            old_plates = {rec.id: rec.license_plate for rec in self}
        result = super().write(vals)
        if 'license_plate' in vals and not self.env.context.get('x_skip_plate_history'):
            History = self.env['fleet.vehicle.license.plate.history']
            new_plate = vals['license_plate']
            today = fields.Date.today()
            for rec in self:
                old_plate = old_plates.get(rec.id)
                if old_plate != new_plate and new_plate:
                    last = History.search([
                        ('vehicle_id', '=', rec.id),
                        ('license_plate', '=', old_plate),
                        ('valid_until', '=', False),
                    ], limit=1, order='id desc')
                    if last:
                        last.valid_until = today
                    History.create({
                        'vehicle_id': rec.id,
                        'license_plate': new_plate,
                        'valid_from': None,
                        'valid_until': None,
                    })
        return result

    def action_create_batch_document(self):
        if not self:
            return False

        # 1. Validasi Initial License Plate pada semua kendaraan yang dipilih
        missing_initial_plate = self.filtered(lambda v: not v.initial_license_plate)
        if missing_initial_plate:
            raise ValidationError(
                _("Proses pembuatan batch document dibatalkan karena kendaraan berikut belum memiliki Initial License Plate:\n%s")
                % '\n'.join(missing_initial_plate.mapped(lambda v: v.name or v.display_name))
            )

        # 2. Validasi kendaraan yang sudah memiliki dokumen running bertipe is_license_plate
        vehicles_with_running_plate_doc = self.filtered(
            lambda v: v.log_contracts.filtered(
                lambda c: c.state == 'open' and c.cost_subtype_id.is_license_plate
            )
        )
        if vehicles_with_running_plate_doc:
            raise ValidationError(
                _("Proses pembuatan batch document dibatalkan karena kendaraan berikut sudah memiliki dokumen plat (Is License Plate) dengan status Running:\n%s")
                % '\n'.join(vehicles_with_running_plate_doc.mapped(lambda v: v.name or v.display_name))
            )

        # 3. Cari tipe dokumen (fleet.service.type) dengan is_license_plate = True
        ServiceType = self.env['fleet.service.type']
        doc_type = ServiceType.search([
            ('is_license_plate', '=', True),
            ('category', '=', 'contract')
        ], limit=1)
        if not doc_type:
            doc_type = ServiceType.search([
                ('is_license_plate', '=', True)
            ], limit=1)

        if not doc_type:
            raise ValidationError(
                _("Tipe dokumen dengan flag 'Is License Plate' tidak ditemukan. Harap konfigurasikan tipe dokumen terlebih dahulu.")
            )

        # 4. Pastikan kendaraan memiliki asset_number, jika belum maka generate asset_number
        for vehicle in self:
            if not vehicle.asset_number:
                seq = self.env['ir.sequence'].next_by_code('asset.serial.number')
                if not seq:
                    raise ValidationError(_("Sequence 'asset.serial.number' tidak ditemukan untuk pembuatan Asset Number."))
                vehicle.write({'asset_number': seq})

        # 5. Tanggal start hari ini dan expiration satu tahun dari start date
        today = fields.Date.context_today(self)
        expiration_date = today + relativedelta(years=1)

        Contract = self.env['fleet.vehicle.log.contract']
        vals_list = []
        for vehicle in self:
            plate = Contract.format_license_plate_input(vehicle.initial_license_plate) or vehicle.initial_license_plate
            vals = {
                'vehicle_id': vehicle.id,
                'cost_subtype_id': doc_type.id,
                'license_plate': plate,
                'start_date': today,
                'expiration_date': expiration_date,
                'asset_number': vehicle.asset_number,
                'vin_number': getattr(vehicle, 'chassis_number', None) or vehicle.vin_sn or '',
                'company_id': vehicle.company_id.id if vehicle.company_id else self.env.company.id,
                'user_id': vehicle.manager_id.id if vehicle.manager_id else self.env.user.id,
            }
            vals_list.append(vals)

        created_contracts = Contract.create(vals_list)
        # Set status dokumen langsung menjadi Running ('open')
        created_contracts.write({'state': 'open'})

        if len(created_contracts) == 1:
            return {
                'name': _('Document'),
                'type': 'ir.actions.act_window',
                'res_model': 'fleet.vehicle.log.contract',
                'res_id': created_contracts.id,
                'view_mode': 'form',
                'views': [(False, 'form')],
            }
        return {
            'name': _('Documents'),
            'type': 'ir.actions.act_window',
            'res_model': 'fleet.vehicle.log.contract',
            'domain': [('id', 'in', created_contracts.ids)],
            'view_mode': 'list,form',
            'views': [(False, 'list'), (False, 'form')],
        }

    def return_action_to_open(self):
        res = super().return_action_to_open()
        if isinstance(res, dict) and 'context' in res:
            res_context = dict(res['context'])
            res_context.update({
                'active_id': self.id,
                'active_ids': [self.id],
                'active_model': 'fleet.vehicle',
            })
            res['context'] = res_context
        return res

