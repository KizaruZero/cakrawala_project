from odoo import models, fields, api

class BastkSubmitWizard(models.TransientModel):
    _name = 'bastk.submit.wizard'
    _description = 'BASTK Submit Wizard'

    bastk_id = fields.Many2one('bastk.management', string="BASTK", required=True, ondelete='cascade')
    submit_type = fields.Selection([('out', 'Keluar'), ('in', 'Masuk')], string="Submit Type", required=True)

    pic = fields.Char(string="PIC", required=True)
    call_number = fields.Char(string="Call Number", required=True)
    odometer = fields.Float(string="Odometer", required=True)
    date = fields.Date(string="Tanggal", required=True, default=fields.Date.context_today)

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        if self.env.context.get('active_id') and self.env.context.get('active_model') == 'bastk.management':
            bastk = self.env['bastk.management'].browse(self.env.context.get('active_id'))
            res['bastk_id'] = bastk.id
            if self.env.context.get('default_submit_type') == 'out':
                res['pic'] = bastk.pic_keluar
                res['call_number'] = bastk.call_number_keluar
                res['odometer'] = bastk.odometer_out or bastk.last_odometer
                if bastk.start_date:
                    res['date'] = bastk.start_date
            elif self.env.context.get('default_submit_type') == 'in':
                res['pic'] = bastk.pic_masuk
                res['call_number'] = bastk.call_number_masuk
                res['odometer'] = bastk.odometer_in or bastk.last_odometer
                if bastk.end_date:
                    res['date'] = bastk.end_date
        return res

    def action_confirm(self):
        self.ensure_one()
        if self.submit_type == 'out':
            self.bastk_id.write({
                'pic_keluar': self.pic,
                'call_number_keluar': self.call_number,
                'odometer_out': self.odometer,
                'start_date': self.date,
            })
            self.bastk_id.with_context(skip_submit_wizard=True).action_submit_outside()
        elif self.submit_type == 'in':
            self.bastk_id.write({
                'pic_masuk': self.pic,
                'call_number_masuk': self.call_number,
                'odometer_in': self.odometer,
                'end_date': self.date,
            })
            self.bastk_id.with_context(skip_submit_wizard=True).action_submit_inside()
