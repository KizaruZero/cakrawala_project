from odoo import fields, models


class CleanupLog(models.Model):
    """ What was deleted, by whom. Its table is protected: no cleanup ever touches it. """
    _name = 'x.cleanup.log'
    _description = 'Data Cleanup: Log'
    _order = 'id desc'

    name = fields.Char(string='Ringkasan', required=True, readonly=True)
    date = fields.Datetime(string='Waktu', default=fields.Datetime.now, readonly=True)
    user_login = fields.Char(string='User', readonly=True)
    database = fields.Char(string='Database', readonly=True)
    mode = fields.Selection([('records', 'Record terpilih'), ('all', 'Semua transaksi'),
                             ('sequence', 'Reset sequence')], string='Mode', readonly=True)
    total_deleted = fields.Integer(string='Baris Dihapus', readonly=True)
    total_nullified = fields.Integer(string='Referensi Dikosongkan', readonly=True)
    options = fields.Text(string='Opsi', readonly=True)
    details = fields.Text(string='Detail per Tabel', readonly=True)
    post_notes = fields.Text(string='Tindak Lanjut', readonly=True)
