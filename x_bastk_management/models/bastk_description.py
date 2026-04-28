from odoo import models, fields, api


class BastkDescription(models.Model):
    _name = 'bastk.description'
    _description = 'BASTK Description'

    bastk_id = fields.Many2one('bastk.management', required=True, ondelete='cascade')
    checklist_id = fields.Many2one('bastk.master.description', required=True)
    bastk_type = fields.Selection([
        ('keluar', 'Keluar'),
        ('masuk', 'Masuk'),
    ], required=True)

    condition = fields.Selection([
        ('baik', 'Baik'),
        ('tidak_ada', 'Tidak Ada'),
        ('rusak', 'Rusak'),
        ('hilang', 'Hilang'),
    ])
    condition_baik = fields.Boolean(string='Baik', compute='_compute_condition_flags', inverse='_inverse_condition_baik')
    condition_tidak_ada = fields.Boolean(string='Tidak Ada', compute='_compute_condition_flags', inverse='_inverse_condition_tidak_ada')
    condition_rusak = fields.Boolean(string='Rusak', compute='_compute_condition_flags', inverse='_inverse_condition_rusak')
    condition_hilang = fields.Boolean(string='Hilang', compute='_compute_condition_flags', inverse='_inverse_condition_hilang')

    remarks = fields.Text()

    @api.depends('condition')
    def _compute_condition_flags(self):
        for rec in self:
            rec.condition_baik = rec.condition == 'baik'
            rec.condition_tidak_ada = rec.condition == 'tidak_ada'
            rec.condition_rusak = rec.condition == 'rusak'
            rec.condition_hilang = rec.condition == 'hilang'

    def _inverse_condition_baik(self):
        for rec in self:
            if rec.condition_baik:
                rec.condition = 'baik'

    def _inverse_condition_tidak_ada(self):
        for rec in self:
            if rec.condition_tidak_ada:
                rec.condition = 'tidak_ada'

    def _inverse_condition_rusak(self):
        for rec in self:
            if rec.condition_rusak:
                rec.condition = 'rusak'

    def _inverse_condition_hilang(self):
        for rec in self:
            if rec.condition_hilang:
                rec.condition = 'hilang'
