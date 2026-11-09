from odoo import api, fields, models


RENTAL_QUOTATION_TERMS = """
<p><strong>Term and Conditions:</strong></p>
<table class="table table-borderless" style="width: 100%;">
  <tbody><tr>
    <td style="width: 50%; vertical-align: top; padding-right: 16px;">
      <p><strong>Harga diatas sudah termasuk:</strong></p>
      <ol>
        <li>Biaya perbaikan dan perawatan.</li>
        <li>Fasilitas kendaraan pengganti.</li>
        <li>Asuransi Comprehensive dengan TPL Sesuai Kontrak</li>
        <li>Layanan bantuan 24 Jam.</li>
        <li>Perpanjangan STNK setiap tahun.</li>
        <li>Kendaraan baru / standar dari dealer setempat (Brand new).</li>
      </ol>
      <p><strong>Harga sewa tidak termasuk:</strong></p>
      <ol>
        <li>PPN (Sesuai Ketentuan dari pemerintah)</li>
        <li>Jasa pengemudi BBM, Tol dan Parkir</li>
        <li>Insurance deductible (own risk) sesuai kontrak</li>
        <li>Biaya E-TLE</li>
        <li>Penggunaan kendaraan yang tidak dicover asuransi</li>
        <li>Penambahan aksesoris kendaraan</li>
      </ol>
    </td>
    <td style="width: 50%; vertical-align: top;">
      <p><strong>Pembayaran:</strong></p>
      <ol>
        <li>Per bulan di muka.</li>
        <li>Pembayaran dilakukan dengan transfer bank.</li>
        <li>TOP 15 hari kerja setelah Invoice diterima oleh customer.</li>
        <li>Biaya keterlambatan pembayaran : 0,2% per hari dari harga sewa.</li>
        <li>Pembatalan sesudah PO diterima atau pemutusan sewa dikenakan penalty / denda 25% dari sisa masa sewa.</li>
      </ol>
    </td>
  </tr></tbody>
</table>
"""


class SaleOrderRentalQuotationTerms(models.Model):
    _inherit = 'sale.order'

    rental_quotation_terms_only = fields.Boolean(
        string='Quotation-only Rental Terms', default=False,
        readonly=True, copy=False,
        help='New rental quotations keep their editable quotation conditions '
             'separate from invoice terms. Existing orders retain their legacy flow.',
    )

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        rental = values.get('is_rental_order', self.env.context.get(
            'default_is_rental_order', self.env.context.get('in_rental_app', False),
        ))
        if rental and 'note' in fields_list and 'default_note' not in self.env.context:
            values['note'] = RENTAL_QUOTATION_TERMS
        return values

    @api.model_create_multi
    def create(self, vals_list):
        rental_default = self.default_get(['is_rental_order']).get('is_rental_order')
        values_list = [dict(values) for values in vals_list]
        for values in values_list:
            if (values.get('is_rental_order', rental_default)
                    and 'note' not in values and 'default_note' not in self.env.context):
                values['note'] = RENTAL_QUOTATION_TERMS
        orders = super().create(values_list)
        # Mark only newly created rentals. No upgrade/migration marks historical
        # orders, so their existing quotation-to-invoice note flow is retained.
        orders.filtered('is_rental_order').write({'rental_quotation_terms_only': True})
        return orders

    def _prepare_invoice(self):
        values = super()._prepare_invoice()
        if self.is_rental_order and self.rental_quotation_terms_only:
            # Leaving the field unset preserves account.move's native invoice
            # terms policy (company/language/settings), rather than copying the
            # quotation's pricing/coverage conditions. Never touch old invoices.
            values.pop('narration', None)
        return values

    @api.depends('partner_id')
    def _compute_note(self):
        # The native partner onchange must not replace these editable rental
        # terms with company invoice terms. Other sales keep the native flow.
        rental_orders = self.filtered('is_rental_order')
        super(SaleOrderRentalQuotationTerms, self - rental_orders)._compute_note()
        for order in rental_orders:
            # Defaults are supplied above. Preserve edits, including an
            # intentionally empty value, instead of re-defaulting on onchange.
            order.note = order.note
