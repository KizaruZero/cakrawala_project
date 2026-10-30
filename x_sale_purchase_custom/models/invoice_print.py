from odoo import fields, models
from odoo.tools import SQL


CUSTOM_INVOICE_REPORT = 'x_sale_purchase_custom.report_invoice_custom'
PRINT_SNAPSHOT = '_cakrawala_invoice_reprint_ids'


class RentalInvoicePrintLog(models.Model):
    _name = 'rental.invoice.print.log'
    _description = 'Custom Invoice PDF Print Tracking'
    _rec_name = 'move_id'

    move_id = fields.Many2one('account.move', required=True, ondelete='cascade', index=True)
    print_count = fields.Integer(default=0, readonly=True, required=True)

    _move_unique = models.Constraint('UNIQUE(move_id)', 'Print tracking must be unique per invoice.')


class IrActionsReport(models.Model):
    _inherit = 'ir.actions.report'

    def _render_qweb_pdf(self, report_ref, res_ids=None, data=None):
        report = self._get_report(report_ref)
        if report.report_name != CUSTOM_INVOICE_REPORT or not res_ids:
            return super()._render_qweb_pdf(report_ref, res_ids=res_ids, data=data)

        ids = [res_ids] if isinstance(res_ids, int) else list(dict.fromkeys(res_ids))
        moves = self.env['account.move'].browse(ids).exists()
        moves.check_access('read')
        invoices = moves.filtered(lambda move: move.move_type in ('out_invoice', 'out_refund'))
        if not invoices:
            return super()._render_qweb_pdf(report_ref, res_ids=res_ids, data=data)

        # Only internal print metadata is written, never the invoice/journal.
        # Accounting read-only users may print without acquiring invoice-write
        # rights. Record access is checked above, before any tracking SQL.
        # Ordered row locks plus ON CONFLICT prevent simultaneous originals.
        # PostgreSQL/Odoo retries serialization conflicts in concurrent requests.
        with self.env.cr.savepoint():
            self.env.cr.execute(SQL('''
                INSERT INTO rental_invoice_print_log
                    (move_id, print_count, create_uid, write_uid, create_date, write_date)
                SELECT id, 0, %s, %s, NOW() AT TIME ZONE 'UTC', NOW() AT TIME ZONE 'UTC'
                  FROM account_move WHERE id IN %s ORDER BY id
                ON CONFLICT (move_id) DO NOTHING
            ''', self.env.uid, self.env.uid, tuple(invoices.ids)))
            self.env.cr.execute(SQL('''
                SELECT move_id, print_count FROM rental_invoice_print_log
                 WHERE move_id IN %s ORDER BY move_id FOR UPDATE
            ''', tuple(invoices.ids)))
            reprints = [move_id for move_id, count in self.env.cr.fetchall() if count > 0]
            renderer = self.with_context(**{PRINT_SNAPSHOT: reprints})
            result = super(IrActionsReport, renderer)._render_qweb_pdf(
                report_ref, res_ids=res_ids, data=data,
            )
            if result[1] == 'pdf' and result[0]:
                self.env.cr.execute(SQL('''
                    UPDATE rental_invoice_print_log
                       SET print_count = print_count + 1, write_uid = %s,
                           write_date = NOW() AT TIME ZONE 'UTC'
                     WHERE move_id IN %s
                ''', self.env.uid, tuple(invoices.ids)))
                self.env['rental.invoice.print.log'].invalidate_model()
            return result

    def _get_rendering_context(self, report, docids, data):
        values = super()._get_rendering_context(report, docids, data)
        if report.report_name == CUSTOM_INVOICE_REPORT:
            moves = values['docs'].exists()
            moves.check_access('read')
            # A PDF uses the locked, pre-render snapshot, overriding any client
            # data/context that might otherwise hide the REPRINT label.
            if PRINT_SNAPSHOT in self.env.context:
                reprints = self.env.context[PRINT_SNAPSHOT]
            elif moves:
                self.env.cr.execute(SQL('''
                    SELECT move_id FROM rental_invoice_print_log
                     WHERE move_id IN %s AND print_count > 0
                ''', tuple(moves.ids)))
                reprints = [row[0] for row in self.env.cr.fetchall()]
            else:
                reprints = []
            values['custom_invoice_reprint_ids'] = reprints
        return values
