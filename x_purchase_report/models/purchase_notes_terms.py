from odoo import api, fields, models
from odoo.tools import is_html_empty


class PurchaseNotesTermsMixin(models.AbstractModel):
    """Notes dibawa dari dokumen asal: RO -> PR -> PO -> Bill. Isi yang sudah ada tidak ditimpa.

    Syarat dan Ketentuan tidak diisi di sini: template company hanya dipakai PR/PO yang
    dibuat dari Rental Order (lihat wizard Create PR/PO di x_sale_purchase_custom), dan
    tidak ikut ke Bill."""
    _name = 'purchase.notes.terms.mixin'
    _description = 'Notes'

    x_notes = fields.Html(string='Notes')

    def _get_default_notes(self):
        return False

    def _fill_notes(self):
        for record in self:
            notes = record._get_default_notes()
            if is_html_empty(record.x_notes) and not is_html_empty(notes):
                record.x_notes = notes

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._fill_notes()
        return records


class PurchaseOrder(models.Model):
    _name = 'purchase.order'
    _inherit = ['purchase.order', 'purchase.notes.terms.mixin']

    def _get_default_notes(self):
        return self.requisition_order_ids[:1].x_notes

    @api.onchange('order_line', 'input_line_ids')
    def _onchange_default_notes(self):
        self._fill_notes()

    def _prepare_invoice(self):
        invoice_vals = super()._prepare_invoice()
        invoice_vals['x_notes'] = self.x_notes
        # Syarat dan Ketentuan stay on the PR/PO: the bill does not carry them.
        invoice_vals.pop('narration', None)
        return invoice_vals


class EmployeePurchaseRequisition(models.Model):
    _name = 'employee.purchase.requisition'
    _inherit = ['employee.purchase.requisition', 'purchase.notes.terms.mixin']


class PurchaseOrderAdvancePayment(models.TransientModel):
    _inherit = 'purchase.order.advance.payment'

    def _prepare_invoice_values(self, order, name, amount, so_line):
        invoice_vals = super()._prepare_invoice_values(order, name, amount, so_line)
        invoice_vals['x_notes'] = order.x_notes
        invoice_vals.pop('narration', None)
        return invoice_vals


class AccountMove(models.Model):
    _inherit = 'account.move'

    x_notes = fields.Html(string='Notes')
