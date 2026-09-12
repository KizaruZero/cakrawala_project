# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError
from dateutil.relativedelta import relativedelta

class LeasingSimulation(models.Model):
    _name = 'leasing.simulation'
    _description = 'Leasing Amortization Simulation'

    name = fields.Char(string='Name', required=True, default='New Simulation')
    jenis_kredit = fields.Selection([
        ('conventional', 'Conventional'),
        ('syariah', 'Syariah'),
    ], string='Jenis Kredit', default='conventional')
    start_date_leasing = fields.Date(string='Leasing Start Date', required=True, default=fields.Date.context_today)
    advarr = fields.Selection([
        ('in_advance_addm', 'In Advanced/ADDM'),
        ('in_arrears', 'In Arrears'),
    ], string='Advarr', default='in_advance_addm')
    
    total_hutang = fields.Float(string='Total Hutang', digits=(16, 2))
    harga_otr = fields.Float(string='Harga OTR', digits=(16, 2))
    down_payment_leasing = fields.Float(string='Down Payment', digits=(16, 2))
    monthly_installment = fields.Float(string='Cicilan Per Bulan', digits=(16, 2))
    
    total_installment_payment = fields.Float(
        string='Total Pembayaran Cicilan', compute='_compute_totals', store=True)
    saldo_pokok_hutang = fields.Float(
        string='Saldo Pokok Hutang', compute='_compute_totals', store=True)
    total_bunga = fields.Float(
        string='Total Bunga', compute='_compute_totals', store=True)
        
    compute_method = fields.Selection([
        ('effective', 'Bunga Efektif'),
        ('flat', 'Bunga Flat'),
    ], string='Compute Method', default='effective', required=True)
    
    interest_rate_annual = fields.Float(string='Interest', digits=(13, 10))
    outstanding_balance = fields.Float(
        string='Outstanding Balance', compute='_compute_totals', store=True)
    duration = fields.Integer(string='Duration', required=True, default=12)
    asset_group = fields.Char(string='Asset Group')
    
    line_ids = fields.One2many('leasing.simulation.line', 'simulation_id', string='Amortization Schedule')

    @api.depends('total_hutang', 'monthly_installment', 'line_ids', 'line_ids.total')
    def _compute_totals(self):
        for rec in self:
            rec.saldo_pokok_hutang = (rec.total_hutang or 0.0) - (rec.monthly_installment or 0.0)
            if rec.line_ids and len(rec.line_ids) > 1:
                rec.total_installment_payment = sum(rec.line_ids[1:].mapped('total'))
            elif rec.monthly_installment and rec.duration > 1:
                rec.total_installment_payment = rec.monthly_installment * (rec.duration - 1)
            else:
                rec.total_installment_payment = 0.0
                
            rec.total_bunga = (rec.total_installment_payment or 0.0) - (rec.saldo_pokok_hutang or 0.0)
            rec.outstanding_balance = rec.total_hutang

    def action_compute_schedule(self):
        for rec in self:
            duration = int(rec.duration) if rec.duration else 0
            if duration <= 0:
                duration = 12
                rec.duration = duration

            otr = rec.harga_otr or 0.0
            dp = rec.down_payment_leasing or 0.0
            cicilan_bulan = rec.monthly_installment or 0.0
            rate_annual = (rec.interest_rate_annual or 0.0) / 100.0
            start_date = rec.start_date_leasing or fields.Date.context_today(rec)

            pokok_hutang_awal = otr - dp if (otr > 0 and dp > 0 and otr > dp) else (rec.total_hutang or 0.0)
            
            if not cicilan_bulan and duration > 0 and pokok_hutang_awal > 0:
                if rate_annual > 0:
                    bunga_per_bulan = (pokok_hutang_awal * rate_annual) / 12.0
                    pokok_per_bulan = pokok_hutang_awal / duration
                    cicilan_bulan = round(pokok_per_bulan + bunga_per_bulan, 2)
                else:
                    cicilan_bulan = round(pokok_hutang_awal / duration, 2)

            rec.line_ids.unlink()
            lines_vals = []
            current_date = start_date

            pokok_1 = min(pokok_hutang_awal, cicilan_bulan) if cicilan_bulan > 0 else pokok_hutang_awal
            bunga_1 = 0.0
            total_1 = cicilan_bulan
            
            saldo_pokok_1 = max(0.0, pokok_hutang_awal - pokok_1)
            saldo_pokok_running = saldo_pokok_1

            lines_vals.append({
                'simulation_id': rec.id,
                'sequence': 1,
                'tanggal': current_date,
                'pokok': pokok_1,
                'bunga': bunga_1,
                'total': total_1,
                'saldo_pokok': saldo_pokok_running,
                'saldo_bunga': 0.0,
            })

            for i in range(2, duration + 1):
                current_date = start_date + relativedelta(months=i-1)
                
                if rec.compute_method == 'flat':
                    bunga_i = round((saldo_pokok_1 * rate_annual) / 12.0, 2)
                    pokok_i = cicilan_bulan - bunga_i
                else: # 'effective'
                    bunga_i = round(saldo_pokok_running * (rate_annual / 12.0), 2)
                    pokok_i = cicilan_bulan - bunga_i

                total_i = cicilan_bulan
                if i == duration:
                    pokok_i = saldo_pokok_running
                    if rec.compute_method == 'flat':
                        bunga_i = round((saldo_pokok_1 * rate_annual) / 12.0, 2)
                    else:
                        bunga_i = round(saldo_pokok_running * (rate_annual / 12.0), 2)
                    total_i = pokok_i + bunga_i

                saldo_pokok_running = max(0.0, saldo_pokok_running - pokok_i)

                lines_vals.append({
                    'simulation_id': rec.id,
                    'sequence': i,
                    'tanggal': current_date,
                    'pokok': pokok_i,
                    'bunga': bunga_i,
                    'total': total_i,
                    'saldo_pokok': saldo_pokok_running,
                    'saldo_bunga': 0.0,
                })

            total_bunga_awal = sum(val['bunga'] for val in lines_vals)
            saldo_bunga_running = total_bunga_awal
            
            for val in lines_vals:
                saldo_bunga_running = max(0.0, saldo_bunga_running - val['bunga'])
                val['saldo_bunga'] = round(saldo_bunga_running, 2)

            self.env['leasing.simulation.line'].create(lines_vals)
            rec.write({
                'monthly_installment': cicilan_bulan,
                'total_hutang': pokok_hutang_awal,
            })


class LeasingSimulationLine(models.Model):
    _name = 'leasing.simulation.line'
    _description = 'Leasing Simulation Line'
    _order = 'sequence, id'

    simulation_id = fields.Many2one('leasing.simulation', string='Simulation', ondelete='cascade')
    sequence = fields.Integer(string='Angsuran Ke')
    tanggal = fields.Date(string='Tanggal')
    pokok = fields.Float(string='Pokok', digits=(16, 2))
    bunga = fields.Float(string='Bunga', digits=(16, 2))
    total = fields.Float(string='Total', digits=(16, 2))
    saldo_pokok = fields.Float(string='Saldo Pokok', digits=(16, 2))
    saldo_bunga = fields.Float(string='Saldo Bunga', digits=(16, 2))
