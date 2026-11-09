from dateutil.relativedelta import relativedelta

from odoo import fields, models, _
from odoo.exceptions import UserError


class AccountLoan(models.Model):
    _inherit = 'account.loan'

    second_installment_due_date = fields.Date(
        string='Due Date Angsuran Ke-2', tracking=True, copy=False,
        help='Tanggal baru angsuran kedua. Klik Ubah Due Date untuk menerapkan '
             'tanggal bulanan berikutnya tanpa mengubah nominal angsuran pertama maupun lainnya.',
    )

    def _check_due_date_rescheduling_allowed(self):
        self.ensure_one()
        self.check_access('write')
        if self.state != 'draft' or self._flat_has_transactions():
            raise UserError(_('Due Date hanya dapat diubah pada Draft yang belum terhubung transaksi.'))

    def write(self, values):
        if 'second_installment_due_date' in values:
            for loan in self:
                if loan.second_installment_due_date != fields.Date.to_date(values['second_installment_due_date']):
                    loan._check_due_date_rescheduling_allowed()
        return super().write(values)

    def action_apply_second_installment_due_date(self):
        self.ensure_one()
        with self.env.cr.savepoint():
            self._lock_for_early_settlement()
            self._check_due_date_rescheduling_allowed()
            anchor = self.second_installment_due_date
            if not anchor:
                raise UserError(_('Isi Due Date Angsuran Ke-2 terlebih dahulu.'))
            lines = self.line_ids.sorted(lambda line: (line.date, line.id))
            if len(lines) < 2:
                raise UserError(_('Minimal dua angsuran harus sudah terbentuk. Klik Compute Jadwal dahulu.'))
            if anchor <= lines[0].date:
                raise UserError(_('Due Date angsuran kedua harus setelah Due Date angsuran pertama.'))
            targets = {line.id: anchor + relativedelta(months=index)
                       for index, line in enumerate(lines[1:])}
            pending = set(targets)
            # Keep the existing line-level chronological/uniqueness checks and
            # signature refreshes. Move only a row that fits between its current
            # neighbours; this also handles shifts beyond several old periods.
            while pending:
                for index, line in enumerate(lines[1:], 1):
                    if line.id not in pending:
                        continue
                    target = targets[line.id]
                    previous = lines[index - 1].date
                    following = lines[index + 1].date if index + 1 < len(lines) else False
                    if target > previous and (not following or target < following):
                        line.date = target
                        pending.remove(line.id)
                        break
                else:
                    raise UserError(_('Jadwal tanggal tidak dapat diubah tanpa mengubah urutan angsuran.'))
            self.message_post(body=_(
                'Due Date angsuran ke-2 dan seterusnya diperbarui mulai %s. '
                'Tanggal angsuran pertama dan nominal pokok/bunga tidak diubah.',
                anchor.strftime('%d-%m-%Y'),
            ))
        return True

    def action_compute_amortization_schedule(self):
        # Keep an explicitly applied/pending second-date anchor when the user
        # subsequently recomputes amounts. No historical schedule is opted in.
        with self.env.cr.savepoint():
            for loan in self.filtered('second_installment_due_date'):
                loan._check_due_date_rescheduling_allowed()
                if loan.due_date and loan.second_installment_due_date <= loan.due_date:
                    raise UserError(_('Due Date angsuran kedua harus setelah Due Date angsuran pertama.'))
            result = super().action_compute_amortization_schedule()
            for loan in self.filtered('second_installment_due_date'):
                loan.action_apply_second_installment_due_date()
            return result
