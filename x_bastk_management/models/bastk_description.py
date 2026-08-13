from odoo import models, fields, api
from odoo.exceptions import ValidationError


class BastkDescription(models.Model):
    _name = 'bastk.description'
    _description = 'BASTK Description'

    bastk_id = fields.Many2one('bastk.management', required=True, ondelete='cascade')
    checklist_id = fields.Many2one('bastk.master.description', required=True)
    bastk_type = fields.Selection([
        ('keluar', 'Keluar'),
        ('masuk', 'Masuk'),
    ], required=True)

    condition_baik = fields.Boolean(string='Baik')
    condition_tidak_ada = fields.Boolean(string='Tidak Ada')
    condition_rusak = fields.Boolean(string='Rusak')
    condition_hilang = fields.Boolean(string='Hilang')

    condition = fields.Selection([
        ('baik', 'Baik'),
        ('tidak_ada', 'Tidak Ada'),
        ('rusak', 'Rusak'),
        ('hilang', 'Hilang'),
    ], compute='_compute_condition', store=True)

    @api.depends('condition_baik', 'condition_tidak_ada', 'condition_rusak', 'condition_hilang')
    def _compute_condition(self):
        for rec in self:
            if rec.condition_baik:
                rec.condition = 'baik'
            elif rec.condition_tidak_ada:
                rec.condition = 'tidak_ada'
            elif rec.condition_rusak:
                rec.condition = 'rusak'
            elif rec.condition_hilang:
                rec.condition = 'hilang'
            else:
                rec.condition = False

    @api.onchange('condition_baik')
    def _onchange_condition_baik(self):
        if self.condition_baik:
            self.condition_tidak_ada = False
            self.condition_rusak = False
            self.condition_hilang = False

    @api.onchange('condition_tidak_ada')
    def _onchange_condition_tidak_ada(self):
        if self.condition_tidak_ada:
            self.condition_baik = False
            self.condition_rusak = False
            self.condition_hilang = False

    @api.onchange('condition_rusak')
    def _onchange_condition_rusak(self):
        if self.condition_rusak:
            self.condition_baik = False
            self.condition_tidak_ada = False
            self.condition_hilang = False

    @api.onchange('condition_hilang')
    def _onchange_condition_hilang(self):
        if self.condition_hilang:
            self.condition_baik = False
            self.condition_tidak_ada = False
            self.condition_rusak = False

    remarks = fields.Text()

    @api.constrains('condition_baik', 'condition_tidak_ada', 'condition_rusak', 'condition_hilang')
    def _check_single_condition(self):
        for rec in self:
            count = sum([bool(rec.condition_baik), bool(rec.condition_tidak_ada), bool(rec.condition_rusak), bool(rec.condition_hilang)])
            if count > 1:
                raise ValidationError("Hanya diperbolehkan memilih 1 pilihan kondisi pada setiap line.")
