from odoo import api, fields, models

class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    is_vehicle = fields.Boolean(
        related='product_id.is_vehicle',
        string='Is Fleet',
        store=False,
    )

    analytic_account_id = fields.Many2one(
        'account.analytic.account',
        string='Analytic Account',
        compute='_compute_analytic_account_id',
        inverse='_inverse_analytic_account_id',
        store=True,
        readonly=False,
        help='For fleet products, pick the analytic account of the specific vehicle. '
             'The selection is limited to analytic accounts of vehicles that belong to '
             'the selected product, mirroring the Goods Receipt behaviour.',
    )

    analytic_account_domain_ids = fields.Many2many(
        'account.analytic.account',
        string='Allowed Analytic Accounts',
        compute='_compute_analytic_account_domain_ids',
        store=False,
    )

    @api.depends('product_id', 'product_id.is_vehicle')
    def _compute_analytic_account_domain_ids(self):
        """Allowed analytic accounts = accounts of fleet vehicles linked to the product.

        Same relationship chain as the Goods Receipt (stock.move.line): product ->
        stock.lot (by product_id) -> asset_number -> fleet.vehicle -> analytic_account_id.
        fleet.vehicle.product_id is computed/non-stored, so we resolve via lots.
        """
        for line in self:
            if line.product_id and line.product_id.is_vehicle:
                lots = self.env['stock.lot'].search([
                    ('product_id', '=', line.product_id.id)
                ])
                asset_numbers = lots.mapped('name')
                if asset_numbers:
                    vehicles = self.env['fleet.vehicle'].search([
                        ('asset_number', 'in', asset_numbers)
                    ])
                    analytic_ids = vehicles.filtered('analytic_account_id').mapped('analytic_account_id').ids
                else:
                    analytic_ids = []
                line.analytic_account_domain_ids = [(6, 0, analytic_ids)]
            else:
                line.analytic_account_domain_ids = [(5, 0, 0)]

    @api.depends('analytic_distribution')
    def _compute_analytic_account_id(self):
        """Mirror the (first) account held in analytic_distribution into a Many2one.

        Keeps the restricted selector in sync when the distribution is set elsewhere
        (e.g. loaded from an existing order, or via the native widget on non-fleet lines).
        """
        for line in self:
            account_id = False
            for key in (line.analytic_distribution or {}):
                head = key.split(',')[0]
                if head.isdigit():
                    account_id = int(head)
                    break
            line.analytic_account_id = account_id

    def _inverse_analytic_account_id(self):
        """Push the chosen analytic account back into analytic_distribution (100%)."""
        for line in self:
            if not line.analytic_account_id:
                continue
            distribution = {str(line.analytic_account_id.id): 100}
            if line.analytic_distribution != distribution:
                line.analytic_distribution = distribution

    def _prepare_procurement_values(self, **kwargs):
        vals = super()._prepare_procurement_values(**kwargs)
        if self.analytic_distribution:
            vals['analytic_distribution'] = self.analytic_distribution
            try:
                first_account_id = next(iter(self.analytic_distribution.keys()))
                vals['analytic_account_id'] = int(first_account_id)
            except Exception:
                pass
        return vals
