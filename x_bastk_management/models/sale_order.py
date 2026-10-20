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
        """Allowed analytic accounts = accounts of fleet vehicles registered for the product
        (fleet.vehicle.lot_id -> stock.lot.product_id), same as the Goods Receipt.
        """
        for line in self:
            if line.product_id and line.product_id.is_vehicle:
                vehicles = self.env['fleet.vehicle'].search([
                    ('lot_id.product_id', '=', line.product_id.id),
                    ('analytic_account_id', '!=', False),
                    # an account of another company cannot be read (nor used) here
                    ('analytic_account_id.company_id', 'in', [False, line.company_id.id]),
                ])
                line.analytic_account_domain_ids = [(6, 0, vehicles.analytic_account_id.ids)]
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

    def write(self, vals):
        res = super().write(vals)
        if 'analytic_distribution' in vals and not self.env.context.get('fleet_analytic_from_delivery'):
            self._push_fleet_analytic_to_deliveries()
        return res

    def _push_fleet_analytic_to_deliveries(self):
        """Choosing another vehicle (analytic account) on a confirmed line moves its
        open delivery to that vehicle's Fleet Number.

        One line = one vehicle: a line of several units is left to the delivery.
        """
        for line in self:
            if not (line.is_vehicle and line.state == 'sale'
                    and line.product_uom_id.compare(line.product_uom_qty, 1.0) == 0):
                continue
            account = line.analytic_account_id
            if not account:
                continue
            for move in line.move_ids.filtered(
                lambda m: m.picking_code == 'outgoing' and m.state not in ('draft', 'done', 'cancel')
                and m._is_fleet_delivery_move()
            ):
                held = move.move_line_ids.filtered('lot_id').analytic_account_id
                if held == account and move.analytic_account_id == account:
                    continue
                move._write_fleet_analytic_distribution({str(account.id): 100})
                if move.state != 'waiting':
                    move._assign_fleet_lots_from_accounts(account, strict=True)
                    move._sync_fleet_analytic_from_lines()

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
