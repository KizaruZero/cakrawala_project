from collections import defaultdict

from markupsafe import Markup

from odoo import _, fields, models

from ..models.cleanup_preset import AREAS


class CleanupDashboard(models.TransientModel):
    _name = 'x.cleanup.dashboard'
    _description = 'Data Cleanup: Dashboard'

    database_name = fields.Char(compute='_compute_dashboard')
    unlocked_until = fields.Datetime(compute='_compute_dashboard', string='Terbuka sampai')
    is_unlocked = fields.Boolean(compute='_compute_dashboard')
    summary_html = fields.Html(compute='_compute_dashboard', sanitize=False)
    total_transactions = fields.Integer(compute='_compute_dashboard', string='Total Record Transaksi')
    review_count = fields.Integer(compute='_compute_dashboard', string='Model Perlu Review')

    def _compute_display_name(self):
        for record in self:
            record.display_name = _('Data Cleanup')

    def _compute_dashboard(self):
        guard = self.env['x.cleanup.guard']
        until = guard.unlocked_until()
        targets = self.env['x.cleanup.target'].sudo().search([('category', '=', 'transaction')])
        by_area = defaultdict(list)
        for target in targets:
            if target.record_count:
                by_area[target.area].append(target)
        rows, total = [], 0
        for key, label in AREAS:
            members = by_area.get(key)
            if not members:
                continue
            count = sum(t.record_count for t in members)
            total += count
            details = Markup(', ').join(Markup('%s <span class="text-muted">(%s)</span>') % (t.name, t.record_count)
                                        for t in sorted(members, key=lambda t: -t.record_count))
            rows.append(Markup('<tr><td class="fw-bold text-nowrap">%s</td><td class="small">%s</td>'
                               '<td class="text-end text-nowrap">%s</td></tr>') % (label, details, '{:,}'.format(count)))
        if rows:
            html = Markup('<table class="table table-sm"><thead><tr><th>Area</th><th>Data</th>'
                          '<th class="text-end">Record</th></tr></thead><tbody>%s</tbody><tfoot><tr>'
                          '<th colspan="2">Total</th><th class="text-end">%s</th></tr></tfoot></table>') % (
                Markup('').join(rows), '{:,}'.format(total))
        else:
            html = Markup('<p class="text-muted">%s</p>') % _('Tidak ada data transaksi.')
        review = self.env['x.cleanup.target'].sudo().search_count([('category', '=', 'review')])
        for record in self:
            record.database_name = self.env.cr.dbname
            record.unlocked_until = until
            record.is_unlocked = bool(until)
            record.summary_html = html
            record.total_transactions = total
            record.review_count = review

    def _reload(self):
        return {'type': 'ir.actions.act_window', 'res_model': self._name, 'view_mode': 'form',
                'views': [(False, 'form')], 'target': 'current', 'name': _('Data Cleanup')}

    def action_unlock(self):
        self.env['x.cleanup.guard'].unlock()
        return self._reload()

    def action_lock(self):
        self.env['x.cleanup.guard'].lock()
        return self._reload()

    def action_delete_all(self):
        return self.env['x.cleanup.wizard'].action_open_all()

    def action_sequences(self):
        return self.env['x.cleanup.sequence.wizard'].action_open()

    def action_load_preset(self):
        self.env['x.cleanup.guard'].check_admin()
        self.env['x.cleanup.target'].action_load_preset()
        return self._reload()

    def action_scan(self):
        self.env['x.cleanup.guard'].check_admin()
        self.env['x.cleanup.target'].action_scan_models()
        return self.env['ir.actions.act_window']._for_xml_id('x_data_cleanup.action_cleanup_target_review')

    def action_targets(self):
        return self.env['ir.actions.act_window']._for_xml_id('x_data_cleanup.action_cleanup_target')
