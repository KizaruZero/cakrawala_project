from odoo import _, api, fields, models
from odoo.exceptions import UserError


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    @api.model_create_multi
    def create(self, vals_list):
        defaults = self.default_get(['is_rental_order', 'company_id'])
        values_list = [dict(values) for values in vals_list]
        for values in values_list:
            if values.get('name', _('New')) not in (False, 'New', _('New')):
                # Preserve explicit names supplied by imports/integrations.
                continue
            is_rental = values.get('is_rental_order', defaults.get('is_rental_order'))
            if not is_rental:
                # Standard Sale allocates its original sale.order sequence.
                continue
            sequence_date = (
                fields.Datetime.context_timestamp(self, fields.Datetime.to_datetime(values['date_order']))
                if values.get('date_order') else None
            )
            number = self.env['ir.sequence'].with_company(
                values.get('company_id', defaults.get('company_id')),
            ).next_by_code('sale.order.rental', sequence_date=sequence_date)
            if not number:
                raise UserError(_('Sequence Rental Order belum tersedia. Upgrade modul Sales Purchase Custom atau periksa konfigurasi sequence.'))
            # Allocate before super(): linked pickings/contracts/chatter must
            # see the final RO reference, without consuming a Sales counter.
            values['name'] = number
        return super().create(values_list)
