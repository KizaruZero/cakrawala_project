import base64
import io
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    rental_type_id = fields.Many2one(
        'vehicle.substatus',
        string='Fleet Sub-status',
        domain=[('is_rental_type', '=', True)],
        ondelete='restrict',
        tracking=True,
        help='Sub-status flagged as Fleet Sub-status in Master Sub Status. '
             'The value picked here is applied as Fleet Sub-Status when the asset is registered.',
    )

    is_asset_registered = fields.Boolean(
        string="Asset Registered",
        compute='_compute_is_asset_registered',
        store=True,
        copy=False,
    )
    has_vehicle_product = fields.Boolean(
        string="Has Vehicle Product",
        compute='_compute_has_vehicle_product',
    )
    fleet_vehicle_ids = fields.Many2many(
        'fleet.vehicle',
        string='Fleet / Vehicles',
        compute='_compute_fleet_vehicle_ids',
        help='Vehicles registered from this goods receipt.',
    )
    fleet_vehicle_count = fields.Integer(
        string='Fleet / Vehicle Count',
        compute='_compute_fleet_vehicle_ids',
    )
    is_from_sales_order = fields.Boolean(
        string="Is From Sales Order",
        compute='_compute_is_from_sales_order',
    )

    def _compute_is_from_sales_order(self):
        for picking in self:
            picking.is_from_sales_order = hasattr(picking, 'sale_id') and bool(picking.sale_id)

    is_bastk_linked = fields.Boolean(
        string="Is BASTK Linked",
        compute='_compute_is_bastk_linked',
    )

    def _compute_is_bastk_linked(self):
        for picking in self:
            picking.is_bastk_linked = hasattr(picking, 'bastk_id') and bool(picking.bastk_id)

    @api.depends(
        'state',
        'picking_type_code',
        'move_line_ids.lot_id',
        'move_ids.product_id.is_vehicle',
    )
    def _compute_is_asset_registered(self):
        FleetVehicle = self.env['fleet.vehicle']
        for picking in self:
            if picking.picking_type_code != 'incoming' or picking.state != 'done':
                picking.is_asset_registered = False
                continue

            lot_lines = picking.move_line_ids.filtered(
                lambda ml: ml.lot_id and ml.product_id.is_vehicle
            )
            if lot_lines:
                all_registered = all(
                    FleetVehicle.search_count([('asset_number', '=', ml.lot_id.name)]) > 0
                    for ml in lot_lines
                )
                picking.is_asset_registered = all_registered
                continue

            picking.is_asset_registered = False

    @api.depends('move_ids.product_id.is_vehicle', 'move_ids.state')
    def _compute_has_vehicle_product(self):
        for picking in self:
            active_moves = picking.move_ids.filtered(
                lambda m: m.state != 'cancel' and m.product_id
            )
            picking.has_vehicle_product = any(
                move.product_id.is_vehicle for move in active_moves
            )

    def button_validate(self):
        """Override Validate: validasi mandatory fields per unit (move_line level)."""
        for picking in self:
            if picking.picking_type_code != 'incoming':
                continue

            missing = []

            # Fleet Sub-status (formerly Rental Type) hanya relevan kalau ada produk fleet (product.is_vehicle)
            # dan GR tidak terhubung dengan BASTK (is_bastk_linked == False).
            has_done_vehicle = any(
                m.product_id.is_vehicle and m.quantity > 0
                for m in picking.move_ids.filtered(lambda m: m.state != 'cancel')
            )
            if has_done_vehicle and not picking.is_bastk_linked and not picking.rental_type_id:
                missing.append('Fleet Sub-status (header GR)')

            for move in picking.move_ids:
                if move.state in ('done', 'cancel'):
                    continue
                if move.product_id.tracking != 'serial':
                    continue

                # Pada partial receipt, lewati move yang kuantitas terimanya 0 (akan jadi backorder)
                if move.quantity <= 0:
                    continue

                is_vehicle = move.product_id.is_vehicle
                product_name = move.product_id.display_name

                if not move.move_line_ids:
                    missing.append(
                        'Detail Operations (produk: %s) — klik tombol Detail untuk mengisi data unit'
                        % product_name
                    )
                    continue

                if move.quantity > move.product_uom_qty:
                    missing.append(
                        'Kuantitas Done (%s) melebihi Demand (%s) untuk produk %s'
                        % (move.quantity, move.product_uom_qty, product_name)
                    )

                for idx, line in enumerate(move.move_line_ids, start=1):
                    unit_label = '%s (unit %d)' % (product_name, idx)

                    if line.quantity >= 1.0:
                        if not line.lot_id and not (line.lot_name or '').strip():
                            missing.append('Serial Number — %s' % unit_label)

                        if is_vehicle:
                            if not (line.initial_license_plate or '').strip():
                                missing.append('Initial License Plate — %s' % unit_label)
                            if not (line.chassis_number or '').strip():
                                missing.append('Chassis Number — %s' % unit_label)
                            if not (line.engine_number or '').strip():
                                missing.append('Engine Number — %s' % unit_label)
                            if not line.vehicle_model_id:
                                missing.append('Model — %s' % unit_label)
                            if not line.vehicle_color_id:
                                missing.append('Warna — %s' % unit_label)
                            if not line.vehicle_year_id:
                                missing.append('Tahun — %s' % unit_label)

            if missing:
                raise UserError(
                    _('Unable to validate GR. Please fill in the following fields:\n- %s')
                    % '\n- '.join(missing)
                )

        return super().button_validate()

    def _default_fleet_vehicle_state_for_gr(self):
        """Prefer is_first_destination; else Non-Leased; else standard Fleet Registered; else any state."""
        VehicleState = self.env['fleet.vehicle.state']
        state = VehicleState.search([('is_first_destination', '=', True)], limit=1)
        if not state:
            state = VehicleState.search([('name', '=', 'Non-Leased')], limit=1)
        if state:
            return state.id
        ref = self.env.ref('fleet.fleet_vehicle_state_registered', raise_if_not_found=False)
        if ref:
            return ref.id
        fallback = VehicleState.search([], limit=1, order='sequence, id')
        return fallback.id if fallback else False

    def _fleet_substatus_from_rental_type(self):
        """The GR rental type IS a vehicle.substatus record now — nothing to map."""
        self.ensure_one()
        return self.rental_type_id

    def _is_auto_fleet_registration_candidate(self):
        """Receipts whose vehicles are registered automatically on Validate.

        Same scope as the manual "Register Fleet Detail" button: purchase-side
        receipts only. A GR coming from a Sales Order or linked to a BASTK
        reference already points at an existing vehicle, so it must never create
        a fleet record of its own.
        """
        self.ensure_one()
        return (
            self.picking_type_code == 'incoming'
            and self.state == 'done'
            and self.has_vehicle_product
            and not self.is_from_sales_order
            and not self.is_bastk_linked
        )

    def _get_fleet_registration_lines(self):
        """Received units to register: one fleet.vehicle per serial line.

        Only the lines of THIS picking are considered, so a partial receipt
        registers exactly what it validated and the backorder registers the rest
        when it is validated in turn.
        """
        self.ensure_one()
        return self.move_line_ids.filtered(
            lambda ml: ml.lot_id and ml.product_id.is_vehicle and ml.quantity >= 1.0
        )

    @api.depends(
        'picking_type_code',
        'move_line_ids.lot_id',
        'move_line_ids.quantity',
        'move_line_ids.product_id.is_vehicle',
    )
    def _compute_fleet_vehicle_ids(self):
        """Vehicles registered from this receipt, for the smart button.

        Same units as the registration itself (``_get_fleet_registration_lines``),
        resolved through the Fleet Number the way ``_find_registered_fleet_vehicle``
        does — so the count matches exactly what this GR registered, and a backorder
        shows only its own units.
        """
        FleetVehicle = self.env['fleet.vehicle']
        for picking in self:
            vehicles = FleetVehicle
            if picking.picking_type_code == 'incoming':
                asset_numbers = [
                    name
                    for name in picking._get_fleet_registration_lines().lot_id.mapped('name')
                    if name
                ]
                if asset_numbers:
                    company = picking.company_id or self.env.company
                    vehicles = FleetVehicle.search([
                        ('asset_number', 'in', asset_numbers),
                        ('company_id', 'in', [company.id, False]),
                    ])
            picking.fleet_vehicle_ids = vehicles
            picking.fleet_vehicle_count = len(vehicles)

    def action_view_fleet_vehicles(self):
        self.ensure_one()
        return self.fleet_vehicle_ids.action_open_fleet_vehicles()

    def _find_registered_fleet_vehicle(self, lot):
        """Duplicate guard: the vehicle already registered for this Fleet Number.

        The Fleet Number sequence is defined per company, so the same number can
        legitimately exist in two companies — scope the lookup to the receipt's
        company (vehicles without a company stay visible to all of them).
        """
        self.ensure_one()
        if not lot.name:
            return self.env['fleet.vehicle']
        company = self.company_id or self.env.company
        return self.env['fleet.vehicle'].sudo().search(
            [
                ('asset_number', '=', lot.name),
                ('company_id', 'in', [company.id, False]),
            ],
            limit=1,
        )

    def _ensure_fleet_analytic_account(self, vehicle):
        """Analytic account for a registered vehicle, named after the Fleet Number.

        x_fleet_document renames this very record to "<plate> - <fleet number>"
        when the plate document is set Running: it reads
        ``vehicle.analytic_account_id`` first, so filling it in here is what keeps
        that step an update instead of a second account.

        Both ``fleet.vehicle.analytic_account_id`` and
        ``account.analytic.account.asset_number`` are added by x_fleet_document,
        which depends on this module — so skip when it is not installed.
        """
        self.ensure_one()
        if 'analytic_account_id' not in self.env['fleet.vehicle']._fields:
            return self.env['account.analytic.account']
        if vehicle.analytic_account_id:
            return vehicle.analytic_account_id
        if not vehicle.asset_number:
            return self.env['account.analytic.account']

        company = self.company_id or vehicle.company_id or self.env.company
        Analytic = self.env['account.analytic.account'].sudo()
        account = Analytic.search(
            [
                ('asset_number', '=', vehicle.asset_number),
                ('company_id', '=', company.id),
            ],
            limit=1,
        )
        if not account:
            plan = self.env['account.analytic.plan'].sudo().search([], limit=1)
            if not plan:
                raise UserError(
                    _('Analytic Plan not found. An analytic plan is required to '
                      'register the analytic account of vehicle %s.')
                    % vehicle.asset_number
                )
            account = Analytic.create({
                'name': vehicle.asset_number,
                'asset_number': vehicle.asset_number,
                'plan_id': plan.id,
                'company_id': company.id,
            })

        vehicle.sudo().write({'analytic_account_id': account.id})
        return account

    def _register_fleet_from_moves(self):
        """Register every received unit as a fleet.vehicle with its analytic account.

        Shared by Validate (automatic) and by the manual fallback button, so the
        duplicate guard is the single place deciding whether a unit is already
        registered. Runs as sudo because the person validating a receipt is an
        Inventory user, who has no write access to Fleet or Analytic Accounting.

        Returns the ids of the vehicles covered by this receipt.
        """
        self.ensure_one()

        default_state_id = self._default_fleet_vehicle_state_for_gr()
        fleet_sub = self._fleet_substatus_from_rental_type()
        company = self.company_id or self.env.company

        vehicle_ids = []
        for line in self._get_fleet_registration_lines():
            existing = self._find_registered_fleet_vehicle(line.lot_id)
            if existing:
                vehicle_ids.append(existing.id)
                self._ensure_fleet_analytic_account(existing)
                continue

            model = line.vehicle_model_id or line.lot_id.vehicle_model_id
            if not model:
                raise UserError(
                    _('Model kendaraan belum ditentukan pada line %s.') % line.lot_id.name
                )

            vehicle_vals = {
                'model_id': model.id,
                'asset_number': line.lot_id.name,
                'chassis_number': line.chassis_number or line.lot_id.chassis_number or '',
                'engine_number': line.engine_number or line.lot_id.engine_number or '',
                'initial_license_plate': line.initial_license_plate or line.lot_id.initial_license_plate or '',
                'fleet_sub_status_id': fleet_sub.id if fleet_sub else False,
                'state_id': default_state_id,
                'model_year': line.vehicle_year_id.name if line.vehicle_year_id else '',
                'color': line.vehicle_color_id.name if line.vehicle_color_id else '',
                'company_id': company.id,
            }
            vehicle = self.env['fleet.vehicle'].sudo().create(vehicle_vals)
            vehicle_ids.append(vehicle.id)
            self._ensure_fleet_analytic_account(vehicle)

            lot_vals = {}
            if line.vehicle_model_id:
                lot_vals['vehicle_model_id'] = line.vehicle_model_id.id
            if line.vehicle_year_id:
                lot_vals['vehicle_year_id'] = line.vehicle_year_id.id
            if line.vehicle_color_id:
                lot_vals['vehicle_color_id'] = line.vehicle_color_id.id
            if lot_vals:
                line.lot_id.with_context(skip_sync_fleet=True).write(lot_vals)

        self._compute_is_asset_registered()
        return vehicle_ids

    def _action_done(self):
        """Register the received vehicles once the transfer is really done.

        This is the hook rather than button_validate(): on a partial receipt
        button_validate() returns the backorder wizard and bails out before
        _action_done() is ever reached. _action_done() runs exactly once per
        picking, after the backorder split, so each GR registers only the units
        it actually validated.
        """
        res = super()._action_done()
        for picking in self:
            if picking._is_auto_fleet_registration_candidate():
                picking._register_fleet_from_moves()
        return res

    def action_register_asset_detail(self):
        """Manual fallback for receipts the automatic registration did not cover.

        Registration normally happens on Validate; this button stays available for
        goods receipts validated before that behaviour existed, and hides itself
        again as soon as every unit is registered (is_asset_registered).
        """
        self.ensure_one()

        vehicle_ids = self._register_fleet_from_moves()

        if not vehicle_ids:
            raise UserError(
                _('No vehicle serial numbers found. Please generate Serial Numbers for each '
                  'vehicle unit in the Detailed Operations before registering.')
            )

        if len(vehicle_ids) == 1:
            return {
                'name': _('Fleet Registration'),
                'type': 'ir.actions.act_window',
                'res_model': 'fleet.vehicle',
                'view_mode': 'form',
                'res_id': vehicle_ids[0],
                'target': 'current',
                'context': dict(self.env.context, active_id=vehicle_ids[0], active_ids=[vehicle_ids[0]]),
            }

        return {
            'name': _('Fleet Registration'),
            'type': 'ir.actions.act_window',
            'res_model': 'fleet.vehicle',
            'view_mode': 'list,form',
            'domain': [('id', 'in', vehicle_ids)],
            'target': 'current',
            'context': dict(self.env.context, active_id=False, active_ids=vehicle_ids),
        }

    def action_mass_generate_fn(self):
        for picking in self:
            picking.move_ids.action_mass_generate_fn()
        return True

    def action_export_fn_excel(self):
        """Export data line receipt yang sudah punya FN ke file Excel (.xlsx)."""
        self.ensure_one()
        active_moves = self.move_ids.filtered(lambda m: m.state != 'cancel')
        move_to_line_no = {
            move.id: idx
            for idx, move in enumerate(active_moves, start=1)
        }
        vehicle_moves = active_moves.filtered(lambda m: m.product_id.is_vehicle)

        has_fn = any(
            (l.lot_id or l.lot_name)
            for m in vehicle_moves
            for l in m.move_line_ids
        )
        if not vehicle_moves or not has_fn:
            raise UserError(
                _('Belum ada line penerimaan dengan Fleet Number (FN). '
                  'Silakan jalankan "Mass Generate FN" terlebih dahulu.')
            )

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Receipt FN Details"

        headers = [
            "Line No",
            "Product",
            "Chassis Number",
            "Engine Number",
            "Initial License Plate",
            "Model",
            "Warna",
            "Tahun",
            "Fleet Number",
        ]
        ws.append(headers)

        header_fill = PatternFill(start_color="1F4E78", end_color="1F4E78", fill_type="solid")
        header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
        thin_border = Border(
            left=Side(style='thin', color='D9D9D9'),
            right=Side(style='thin', color='D9D9D9'),
            top=Side(style='thin', color='D9D9D9'),
            bottom=Side(style='thin', color='D9D9D9'),
        )

        for col_num in range(1, len(headers) + 1):
            cell = ws.cell(row=1, column=col_num)
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal="center", vertical="center")

        row_idx = 1
        for move in vehicle_moves:
            line_no = move_to_line_no[move.id]
            move_vehicle_lines = move.move_line_ids.filtered(
                lambda l: l.lot_id or l.lot_name
            )
            for line in move_vehicle_lines:
                fn = line.lot_id.name or line.lot_name or ''
                product_name = line.product_id.display_name or line.product_id.name or ''
                chassis = line.chassis_number or ''
                engine = line.engine_number or ''
                plate = line.initial_license_plate or ''
                model_name = line.vehicle_model_id.name if line.vehicle_model_id else ''
                warna = line.vehicle_color_id.name if line.vehicle_color_id else ''
                tahun = line.vehicle_year_id.name if line.vehicle_year_id else ''

                row = [
                    line_no,
                    product_name,
                    chassis,
                    engine,
                    plate,
                    model_name,
                    warna,
                    tahun,
                    fn,
                ]
                ws.append(row)
                row_idx += 1
                for col_idx in range(1, len(headers) + 1):
                    c = ws.cell(row=row_idx, column=col_idx)
                    c.border = thin_border
                    if col_idx in (1, 7, 8, 9):
                        c.alignment = Alignment(horizontal="center", vertical="center")

        for col in ws.columns:
            max_len = max(len(str(cell.value or '')) for cell in col)
            col_letter = get_column_letter(col[0].column)
            ws.column_dimensions[col_letter].width = max(max_len + 4, 14)

        # ----------------------------------------------------
        # Sheet 2: Referensi Model Kendaraan + Petunjuk/Keterangan
        # ----------------------------------------------------
        ws_model_ref = wb.create_sheet(title="Referensi Model")

        ws_model_ref.merge_cells("A1:C1")
        ws_model_ref["A1"] = "PETUNJUK & REFERENSI MODEL KENDARAAN"
        ws_model_ref["A1"].font = Font(name="Calibri", size=11, bold=True, color="1F4E78")

        ws_model_ref.merge_cells("A2:C2")
        ws_model_ref["A2"] = (
            "1. Anda dapat mengisi kolom 'Model' pada sheet 'Receipt FN Details' mengacu pada daftar referensi model di bawah ini sesuai Manufacturer produk."
        )
        ws_model_ref["A2"].font = Font(name="Calibri", size=10, color="495057")

        ws_model_ref.merge_cells("A3:C3")
        ws_model_ref["A3"] = (
            "2. CATATAN PENTING: Pengisian nama model HARUS SESUAI dengan referensi yang terdaftar di bawah. "
            "Apabila model yang diisi tidak cocok / typo, sistem TIDAK AKAN mengisinya otomatis (dikosongkan) dan akan meminta Anda melengkapi secara manual."
        )
        ws_model_ref["A3"].font = Font(name="Calibri", size=10, bold=True, color="B25900")

        ws_model_ref.merge_cells("A4:C4")
        ws_model_ref["A4"] = "3. Penulisan nama model tidak sensitif huruf besar/kecil (case-insensitive)."
        ws_model_ref["A4"].font = Font(name="Calibri", size=10, color="495057")

        # Header Tabel Model di Baris 6
        model_headers = {
            1: ("No", "center", 8),
            2: ("Manufacturer", "left", 24),
            3: ("Model Kendaraan (Terdaftar)", "left", 32),
        }
        for col_idx, (header_text, align_h, col_width) in model_headers.items():
            c = ws_model_ref.cell(row=6, column=col_idx, value=header_text)
            c.fill = header_fill
            c.font = header_font
            c.alignment = Alignment(horizontal=align_h, vertical="center")
            col_letter = get_column_letter(col_idx)
            ws_model_ref.column_dimensions[col_letter].width = col_width

        brands = vehicle_moves.mapped('product_id.fleet_brand_id')
        if brands:
            models_records = self.env['fleet.vehicle.model'].search(
                [('brand_id', 'in', brands.ids)], order='brand_id, name asc'
            )
        else:
            models_records = self.env['fleet.vehicle.model'].search([], order='brand_id, name asc')

        m_idx = 7
        for idx, m_rec in enumerate(models_records, start=1):
            c_no = ws_model_ref.cell(row=m_idx, column=1, value=idx)
            c_no.border = thin_border
            c_no.alignment = Alignment(horizontal="center", vertical="center")

            c_brand = ws_model_ref.cell(row=m_idx, column=2, value=m_rec.brand_id.name if m_rec.brand_id else '-')
            c_brand.border = thin_border
            c_brand.alignment = Alignment(horizontal="left", vertical="center")

            c_name = ws_model_ref.cell(row=m_idx, column=3, value=m_rec.name)
            c_name.border = thin_border
            c_name.alignment = Alignment(horizontal="left", vertical="center")
            m_idx += 1

        # ----------------------------------------------------
        # Sheet 3: Referensi Warna & Tahun + Petunjuk/Keterangan
        # ----------------------------------------------------
        ws_ref = wb.create_sheet(title="Referensi Warna & Tahun")

        # Judul & Keterangan Panduan
        ws_ref.merge_cells("A1:E1")
        ws_ref["A1"] = "PETUNJUK & REFERENSI MASTER DATA"
        ws_ref["A1"].font = Font(name="Calibri", size=11, bold=True, color="1F4E78")

        ws_ref.merge_cells("A2:E2")
        ws_ref["A2"] = "1. Anda dapat mengisi kolom 'Warna' dan 'Tahun' pada sheet 'Receipt FN Details' mengacu pada tabel referensi di bawah."
        ws_ref["A2"].font = Font(name="Calibri", size=10, color="495057")

        ws_ref.merge_cells("A3:E3")
        ws_ref["A3"] = (
            "2. CATATAN PENTING: Pengisian nama warna dan tahun HARUS SESUAI dengan referensi yang terdaftar di bawah. "
            "Apabila warna/tahun yang diisi tidak cocok / typo, sistem TIDAK AKAN mengisinya otomatis (dikosongkan) dan akan meminta Anda melengkapi secara manual."
        )
        ws_ref["A3"].font = Font(name="Calibri", size=10, bold=True, color="B25900")

        ws_ref.merge_cells("A4:E4")
        ws_ref["A4"] = "3. Penulisan nama warna dan tahun tidak sensitif huruf besar/kecil (sistem akan otomatis memformat huruf kapital di awal kata)."
        ws_ref["A4"].font = Font(name="Calibri", size=10, color="495057")

        # Header Tabel Referensi di Baris 6
        ref_headers = {
            1: ("No", "center"),
            2: ("Referensi Warna (Terdaftar)", "left"),
            3: ("", "center"),
            4: ("No", "center"),
            5: ("Referensi Tahun (Terdaftar)", "center"),
        }
        for col_idx, (header_text, align_h) in ref_headers.items():
            if col_idx == 3:
                continue
            c = ws_ref.cell(row=6, column=col_idx, value=header_text)
            c.fill = header_fill
            c.font = header_font
            c.alignment = Alignment(horizontal=align_h, vertical="center")

        colors = self.env['vehicle.color'].search([], order='name asc')
        years = self.env['vehicle.year'].search([], order='name desc')
        color_list = [c.name for c in colors if c.name]
        year_list = [y.name for y in years if y.name]

        max_ref_rows = max(len(color_list), len(year_list), 1)
        for i in range(max_ref_rows):
            r_idx = 7 + i
            if i < len(color_list):
                c_no = ws_ref.cell(row=r_idx, column=1, value=i + 1)
                c_no.border = thin_border
                c_no.alignment = Alignment(horizontal="center", vertical="center")

                c_val = ws_ref.cell(row=r_idx, column=2, value=color_list[i])
                c_val.border = thin_border
                c_val.alignment = Alignment(horizontal="left", vertical="center")

            if i < len(year_list):
                y_no = ws_ref.cell(row=r_idx, column=4, value=i + 1)
                y_no.border = thin_border
                y_no.alignment = Alignment(horizontal="center", vertical="center")

                y_val = ws_ref.cell(row=r_idx, column=5, value=year_list[i])
                y_val.border = thin_border
                y_val.alignment = Alignment(horizontal="center", vertical="center")

        max_color_len = max([len(str(c)) for c in color_list] or [20])
        ws_ref.column_dimensions['A'].width = 8
        ws_ref.column_dimensions['B'].width = max(max_color_len + 6, 28)
        ws_ref.column_dimensions['C'].width = 4
        ws_ref.column_dimensions['D'].width = 8
        ws_ref.column_dimensions['E'].width = 24

        # Pastikan active sheet saat pertama dibuka adalah sheet utama
        wb.active = ws

        output = io.BytesIO()
        wb.save(output)
        output.seek(0)

        filename = f"FN_Receipt_{self.name.replace('/', '_')}.xlsx"
        attachment = self.env['ir.attachment'].create({
            'name': filename,
            'type': 'binary',
            'datas': base64.b64encode(output.getvalue()),
            'res_model': self._name,
            'res_id': self.id,
            'mimetype': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        })

        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{attachment.id}?download=true',
            'target': 'self',
        }

    def action_open_import_fn_wizard(self):
        """Buka wizard untuk import data kendaraan dari file Excel."""
        self.ensure_one()
        if self.state in ('done', 'cancel'):
            raise UserError(_('Tidak dapat mengimpor data pada penerimaan yang sudah selesai atau dibatalkan.'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Import Data FN Excel'),
            'res_model': 'stock.picking.import.fn.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_picking_id': self.id,
            },
        }

