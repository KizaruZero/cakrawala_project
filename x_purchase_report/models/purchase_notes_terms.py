from odoo import api, fields, models
from odoo.tools import is_html_empty


class PurchaseNotesTermsMixin(models.AbstractModel):
    """Notes (dibawa dari dokumen asal: RO -> PR -> PO -> Bill) dan Detail Description
    (Syarat dan Ketentuan) yang terisi dari template company bila dokumen berisi produk
    Fleet. Isi yang sudah ada tidak ditimpa."""
    _name = 'purchase.notes.terms.mixin'
    _description = 'Notes & Syarat dan Ketentuan'
    _fleet_terms_field = None

    x_notes = fields.Html(string='Notes')

    def _get_fleet_terms_products(self):
        return self.env['product.product']

    def _get_default_notes(self):
        return False

    def _fill_notes_and_terms(self):
        for record in self:
            notes = record._get_default_notes()
            if is_html_empty(record.x_notes) and not is_html_empty(notes):
                record.x_notes = notes
            terms = record.company_id.purchase_fleet_terms
            if (is_html_empty(record[self._fleet_terms_field]) and not is_html_empty(terms)
                    and any(record._get_fleet_terms_products().mapped('is_vehicle'))):
                record[self._fleet_terms_field] = terms

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._fill_notes_and_terms()
        return records


class PurchaseOrder(models.Model):
    _name = 'purchase.order'
    _inherit = ['purchase.order', 'purchase.notes.terms.mixin']
    _fleet_terms_field = 'note'

    def _get_fleet_terms_products(self):
        return self.order_line.product_id | self.input_line_ids.product_id

    def _get_default_notes(self):
        return self.requisition_order_ids[:1].x_notes

    @api.onchange('order_line', 'input_line_ids')
    def _onchange_fleet_terms(self):
        self._fill_notes_and_terms()

    def _prepare_invoice(self):
        invoice_vals = super()._prepare_invoice()
        invoice_vals['x_notes'] = self.x_notes
        return invoice_vals


class EmployeePurchaseRequisition(models.Model):
    _name = 'employee.purchase.requisition'
    _inherit = ['employee.purchase.requisition', 'purchase.notes.terms.mixin']
    _fleet_terms_field = 'detail_description'

    def _get_fleet_terms_products(self):
        return self.requisition_order_ids.product_id

    @api.onchange('requisition_order_ids')
    def _onchange_fleet_terms(self):
        self._fill_notes_and_terms()


class PurchaseOrderAdvancePayment(models.TransientModel):
    _inherit = 'purchase.order.advance.payment'

    def _prepare_invoice_values(self, order, name, amount, so_line):
        invoice_vals = super()._prepare_invoice_values(order, name, amount, so_line)
        invoice_vals['x_notes'] = order.x_notes
        return invoice_vals


class AccountMove(models.Model):
    _inherit = 'account.move'

    x_notes = fields.Html(string='Notes')
