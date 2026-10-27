# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from collections import OrderedDict


class ReportVehiclePnl(models.AbstractModel):
    _name = 'report.x_vehicle_pnl_report.report_vehicle_pnl_document'
    _description = 'Report Engine Parser Laba Rugi Kendaraan'

    @api.model
    def _get_report_values(self, docids, data=None):
        docs = self.env['vehicle.pnl.report.wizard'].browse(docids)
        reports_data = []

        for wizard in docs:
            date_to = wizard.date_to or fields.Date.context_today(self)
            per_tanggal_str = date_to.strftime('%d-%b-%Y').upper() if date_to else '-'

            # Ambil seluruh baris kendaraan yang dicentang
            selected_lines = wizard.line_ids.filtered('selected')
            if not selected_lines:
                selected_lines = wizard.line_ids[:1]

            for line in selected_lines:
                vehicle = line.vehicle_id
                nopol = vehicle.license_plate if vehicle and vehicle.license_plate else (line.license_plate or '-')
                
                # Resolusi akun analitik
                analytic_account = vehicle.analytic_account_id if vehicle else line.analytic_account_id
                if not analytic_account and vehicle:
                    analytic_account = self.env['account.analytic.account'].search([
                        '|', ('license_plate', '=', vehicle.license_plate), ('vehicle_id', '=', vehicle.id)
                    ], limit=1)

                # 1. Info Header Kendaraan
                if vehicle and vehicle.product_id:
                    merk_tipe = vehicle.product_id.display_name or vehicle.product_id.name
                elif vehicle and vehicle.model_id:
                    brand = vehicle.model_id.brand_id.name if vehicle.model_id.brand_id else ''
                    model = vehicle.model_id.name if vehicle.model_id else ''
                    if brand and brand.lower() != 'other' and brand.lower() not in model.lower():
                        merk_tipe = f"{brand} {model}".strip()
                    else:
                        merk_tipe = model or brand or vehicle.name or '-'
                else:
                    merk_tipe = vehicle.name if vehicle else '-'

                # Sisa Pokok / Lama
                loan = False
                if vehicle:
                    loan = self.env['account.loan'].search([
                        ('vehicle_id', '=', vehicle.id),
                        ('state', '=', 'running')
                    ], limit=1, order='id desc')
                    if not loan and vehicle.license_plate:
                        loan = self.env['account.loan'].search([
                            ('plate_number', '=', vehicle.license_plate),
                            ('state', '=', 'running')
                        ], limit=1, order='id desc')

                if loan:
                    sisa_pokok = loan.outstanding_balance or 0.0
                    sisa_lama = loan.remaining_loan or 0
                    sisa_pokok_lama_str = f"{sisa_pokok:,.0f} / {sisa_lama} bln"
                else:
                    sisa_pokok_lama_str = "- / - bln"

                # 2. Query Transaksi Analitik
                income_groups = OrderedDict()
                expense_groups = OrderedDict()
                total_pendapatan = 0.0
                total_biaya = 0.0

                if analytic_account:
                    analytic_lines = self.env['account.analytic.line'].search([
                        ('account_id', '=', analytic_account.id),
                        ('date', '<=', date_to),
                    ], order='date asc, id asc')

                    for al in analytic_lines:
                        gen = al.general_account_id
                        if not gen:
                            continue
                        
                        acc_type = gen.account_type
                        acc_name = gen.name or ''
                        acc_code = gen.code or ''
                        search_txt = f"{acc_code} {acc_name}".lower()
                        amt = abs(al.amount)
                        al_date_str = f"{al.date.day}-{al.date.strftime('%b')}-{al.date.strftime('%y')}" if al.date else ''

                        # --- PENDAPATAN ---
                        if acc_type in ('income', 'income_other'):
                            if any(k in search_txt for k in ('sewa', 'rent', 'rental', '400000')):
                                ket = 'SEWA'
                            elif any(k in search_txt for k in ('penalti', 'penalty')):
                                ket = 'PENDAPATAN PENALTI'
                            else:
                                ket = acc_name.upper()

                            if ket not in income_groups:
                                income_groups[ket] = {'items': [], 'subtotal': 0.0}
                            income_groups[ket]['items'].append({
                                'name': al.name or ket,
                                'date': al_date_str,
                                'amount': amt,
                            })
                            income_groups[ket]['subtotal'] += amt
                            total_pendapatan += amt

                        # --- BIAYA ---
                        elif acc_type in ('expense', 'expense_depreciation', 'expense_direct_cost'):
                            if any(k in search_txt for k in ('admin', 'bank fee', '4444444', '620000')):
                                ket = 'ADMIN BANK'
                            elif any(k in search_txt for k in ('bunga', 'interest', '3333333')):
                                ket = 'BUNGA BANK'
                            elif any(k in search_txt for k in ('asuransi', 'insurance')):
                                ket = 'ASURANSI ACP' if 'acp' in search_txt else 'ASURANSI'
                            elif any(k in search_txt for k in ('stnk', 'pajak kendaraan')):
                                ket = 'STNK'
                            elif any(k in search_txt for k in ('servis', 'service', 'perawatan', 'maintenance', 'bengkel')):
                                ket = 'SERVIS'
                            elif any(k in search_txt for k in ('keur', 'kir')):
                                ket = 'KEUR'
                            else:
                                ket = acc_name.upper()

                            if ket not in expense_groups:
                                expense_groups[ket] = {'items': [], 'subtotal': 0.0}
                            expense_groups[ket]['items'].append({
                                'name': al.name or ket,
                                'date': al_date_str,
                                'amount': amt,
                            })
                            expense_groups[ket]['subtotal'] += amt
                            total_biaya += amt

                total_pendapatan_biaya = total_pendapatan - total_biaya

                # 3. Asset & Summary Box (Grey Box)
                asset = False
                if vehicle:
                    asset = self.env['account.asset'].search([
                        ('vehicle_id', '=', vehicle.id),
                        ('state', '!=', 'model')
                    ], limit=1, order='id desc')

                if asset:
                    beli_hpp = asset.original_value or 0.0
                    depr_moves = asset.depreciation_move_ids.filtered(
                        lambda m: m.state == 'posted' and m.date <= date_to
                    )
                    if depr_moves:
                        amortisasi = sum(depr_moves.mapped('amount_total'))
                    else:
                        amortisasi = max(0.0, asset.original_value - asset.book_value)
                    book_value = max(0.0, beli_hpp - amortisasi)
                    harga_jual = (asset.sell_pl_amount or asset.value_residual) if asset.state in ('sell', 'close', 'dispose') else 0.0
                elif vehicle:
                    beli_hpp = vehicle.car_value or (loan.harga_otr if loan else 0.0) or 0.0
                    amortisasi = 0.0
                    book_value = beli_hpp - amortisasi
                    harga_jual = 0.0
                else:
                    beli_hpp = 0.0
                    amortisasi = 0.0
                    book_value = 0.0
                    harga_jual = 0.0

                laba_rugi = (total_pendapatan_biaya + harga_jual) - book_value

                reports_data.append({
                    'wizard': wizard,
                    'vehicle': vehicle,
                    'nopol': nopol,
                    'merk_tipe': merk_tipe,
                    'sisa_pokok_lama': sisa_pokok_lama_str,
                    'per_tanggal': per_tanggal_str,
                    'income_groups': income_groups,
                    'total_pendapatan': total_pendapatan,
                    'expense_groups': expense_groups,
                    'total_biaya': total_biaya,
                    'total_pendapatan_biaya': total_pendapatan_biaya,
                    'beli_hpp': beli_hpp,
                    'amortisasi': amortisasi,
                    'book_value': book_value,
                    'harga_jual': harga_jual,
                    'laba_rugi': laba_rugi,
                })

        return {
            'doc_ids': docids,
            'doc_model': 'vehicle.pnl.report.wizard',
            'docs': docs,
            'reports_data': reports_data,
        }
