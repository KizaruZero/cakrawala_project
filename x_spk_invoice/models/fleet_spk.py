# -*- coding: utf-8 -*-
from odoo import models, fields, api

class FleetSPK(models.Model):
    _inherit = 'fleet.spk'

    invoice_ids = fields.One2many('account.move', 'fleet_spk_id', string='Invoices')
    invoice_reference = fields.Char(compute='_compute_invoice_reference', string='Invoice Reference')

    total_invoice_amount = fields.Monetary(
        string='Total Invoice',
        currency_field='currency_id',
        compute='_compute_invoice_totals',
        store=True,
        help="Jumlah amount_total dari invoice SPK ini yang sudah di-post. "
             "Invoice draft dan cancelled tidak dihitung.",
    )
    paid_date = fields.Date(
        string='Tanggal Lunas',
        compute='_compute_invoice_totals',
        store=True,
        help="Tanggal pembayaran terakhir, terisi hanya kalau seluruh invoice "
             "yang sudah di-post berstatus Paid atau In Payment.",
    )

    # Invoice dianggap lunas pada dua status. 'paid' berarti sudah direkonsiliasi
    # ke rekening koran; 'in_payment' berarti pembayarannya sudah dicatat tapi
    # rekonsiliasi bank belum dilakukan. Keduanya sama-sama sudah dibayar, dan
    # kalau 'in_payment' tidak dihitung mayoritas invoice akan kosong tanggalnya.
    _PAID_STATES = ('paid', 'in_payment')

    @api.depends(
        'invoice_ids.state',
        'invoice_ids.amount_total',
        'invoice_ids.payment_state',
        'invoice_ids.matched_payment_ids.date',
    )
    def _compute_invoice_totals(self):
        for rec in self:
            posted = rec.invoice_ids.filtered(lambda m: m.state == 'posted')
            rec.total_invoice_amount = sum(posted.mapped('amount_total'))
            rec.paid_date = rec._get_last_payment_date(posted)

    def _get_last_payment_date(self, posted_invoices):
        """Tanggal pembayaran terakhir; False selama masih ada yang belum lunas.

        Sumbernya matched_payment_ids, bukan _get_reconciled_payments(). Di Odoo 19
        payment berstatus 'in_process' belum membuat jurnal sama sekali, jadi belum
        ada baris terekonsiliasi dan _get_reconciled_payments() akan mengembalikan
        kosong walaupun invoice-nya sudah dibayar.

        Fallback ke baris jurnal lawan untuk invoice yang dilunasi lewat rekonsiliasi
        manual/bank statement tanpa account.payment.
        """
        self.ensure_one()
        if not posted_invoices:
            return False
        if any(move.payment_state not in self._PAID_STATES for move in posted_invoices):
            return False

        dates = posted_invoices.matched_payment_ids.mapped('date')
        if not dates:
            dates = posted_invoices._get_reconciled_amls().mapped('date')
        return max(dates) if dates else False

    @api.depends('invoice_ids', 'invoice_ids.state', 'invoice_ids.name')
    def _compute_invoice_reference(self):
        for rec in self:
            refs = []
            for inv in rec.invoice_ids:
                if inv.state == 'draft':
                    refs.append(f"Draft ({inv.name})" if inv.name and inv.name != '/' else "Draft")
                else:
                    refs.append(inv.name or "Draft")
            rec.invoice_reference = ', '.join(refs) if refs else False

    def action_create_invoice(self):
        self.ensure_one()

        analytic_distribution = False
        if hasattr(self.vehicle_id, 'analytic_account_id') and self.vehicle_id.analytic_account_id:
            analytic_distribution = {str(self.vehicle_id.analytic_account_id.id): 100}

        invoice_vals = {
            'move_type': 'in_invoice',
            'partner_id': self.vendor_id.id if self.vendor_id else (self.customer_id.id if self.customer_id else False),
            'ref': self.name,
            'fleet_spk_id': self.id,
            'invoice_line_ids': [(0, 0, {
                'name': self.name,
                'quantity': 1,
                'price_unit': 0,
                'analytic_distribution': analytic_distribution,
            })]
        }

        invoice = self.env['account.move'].create(invoice_vals)

        return {
            'name': 'Vendor Bill',
            'type': 'ir.actions.act_window',
            'view_mode': 'form',
            'res_model': 'account.move',
            'res_id': invoice.id,
            'target': 'current',
        }

    def action_view_invoices(self):
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id("account.action_move_in_invoice_type")
        action['domain'] = [('fleet_spk_id', '=', self.id)]
        action['context'] = {'default_fleet_spk_id': self.id, 'default_move_type': 'in_invoice'}
        return action

