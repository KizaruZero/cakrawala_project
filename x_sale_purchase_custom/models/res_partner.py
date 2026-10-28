from odoo import fields, models


TOP_BILLING_SELECTION = [('didepan', 'Didepan'), ('dibelakang', 'Dibelakang')]
WEEKEND_RULE_SELECTION = [
    ('next_working_day', 'Next Working Day'),
    ('previous_working_day', 'Previous Working Day'),
    ('keep_original', 'Keep Original Date'),
]
BILLING_RULE_SELECTION = [('full_charge', 'Full'), ('prorate', 'Prorate')]
RENTAL_CUSTOMER_DEFAULT_FIELDS = {
    'top_billing': 'rental_default_top_billing',
    'weekend_rule_adjustment': 'rental_default_weekend_rule_adjustment',
    'billing_rule': 'rental_default_billing_rule',
}


class ResPartner(models.Model):
    _inherit = 'res.partner'

    rental_default_top_billing = fields.Selection(
        TOP_BILLING_SELECTION, string='TOP',
        help='Default TOP untuk Rental Order baru. Jika kosong pada kontak anak, mengikuti perusahaan induk. Nilai di order tetap dapat diubah sesuai aturan edit order.',
    )
    rental_default_weekend_rule_adjustment = fields.Selection(
        WEEKEND_RULE_SELECTION, string='Weekend Rule Adjustment',
        help='Default penyesuaian tanggal invoice untuk Rental Order baru. Mengubah default tidak mengubah Rental Order yang sudah ada.',
    )
    rental_default_billing_rule = fields.Selection(
        BILLING_RULE_SELECTION, string='Billing Calculation Method',
        help='Default Full atau Prorate untuk Rental Order baru. Mengubah default tidak menghitung ulang Billing Engine order lama.',
    )

    def _rental_order_billing_defaults(self):
        """Contact overrides company per field; never sync saved order values."""
        self.ensure_one()
        company = self.commercial_partner_id
        return {
            order_field: self[partner_field] or company[partner_field]
            for order_field, partner_field in RENTAL_CUSTOMER_DEFAULT_FIELDS.items()
            if self[partner_field] or company[partner_field]
        }
