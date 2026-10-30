import re

from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tools import SQL


class ResCompany(models.Model):
    _inherit = 'res.company'

    rental_deferred_revenue_model_id = fields.Many2one(
        'account.deferred.model', string='Rental Deferred Revenue Model',
        check_company=True,
        domain="[('company_id', '=', id), ('deferred_type', '=', 'revenue'), ('method_period', '=', 1)]",
        help='Contract-level deferred revenue for TOP Dibelakang. If empty, the '
             'unique active Pendapatan Diterima Di Muka model of this company is used.',
    )


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    rental_deferred_revenue_model_id = fields.Many2one(
        related='company_id.rental_deferred_revenue_model_id', readonly=False,
        domain="[('company_id', '=', company_id), ('deferred_type', '=', 'revenue'), ('method_period', '=', 1)]",
    )


class AccountDeferredEntry(models.Model):
    _inherit = 'account.deferred.entry'

    rental_sale_line_id = fields.Many2one(
        'sale.order.line', string='Rental Order Line', readonly=True, copy=False,
        check_company=True, index=True, ondelete='restrict',
    )
    rental_order_id = fields.Many2one(
        related='rental_sale_line_id.order_id', string='Rental Order', store=True,
    )
    rental_analytic_account_id = fields.Many2one(
        'account.analytic.account', string='Rental Unit Analytic',
        readonly=True, copy=False, check_company=True,
    )
    rental_unit_plate_no = fields.Char(string='Unit Plate No', readonly=True, copy=False)

    _rental_line_unique = models.Constraint(
        'UNIQUE(rental_sale_line_id)', 'A Rental Order line can only have one contract-level deferred revenue item.',
    )

    @api.model_create_multi
    def create(self, values_list):
        source_ids = [values['rental_sale_line_id'] for values in values_list if values.get('rental_sale_line_id')]
        for values in values_list:
            if values.get('rental_sale_line_id'):
                line = self.env['sale.order.line'].browse(values['rental_sale_line_id']).exists()
                line.check_access('read')
                if (not line or not line.product_id or not line.order_id.is_rental_order or line.order_id.state not in ('sale', 'done')
                        or line.order_id.top_billing != 'dibelakang' or not line.actual_delivery_date
                        or line.display_type or line.is_downpayment or line.product_uom_qty <= 0):
                    raise ValidationError(_('Rental deferred revenue requires a confirmed TOP Dibelakang Rental Order line with Actual Delivery Date.'))
        if source_ids:
            sources = self.env['sale.order.line'].browse(source_ids)
            sources.order_id._lock_rental_deferred_orders()
            if len(source_ids) != len(set(source_ids)) or self.with_context(active_test=False).search_count([
                ('rental_sale_line_id', 'in', source_ids),
            ]):
                raise ValidationError(_('A Rental Order line already has a contract-level deferred revenue item.'))
        return super().create(values_list)

    @api.constrains('rental_sale_line_id', 'company_id', 'deferred_type', 'model_id')
    def _check_rental_deferred_source(self):
        for entry in self.filtered('rental_sale_line_id'):
            if (entry.deferred_type != 'revenue' or entry.model_id.deferred_type != 'revenue'
                    or entry.model_id.method_period != 1 or entry.company_id != entry.rental_sale_line_id.company_id):
                raise ValidationError(_('A Rental Order deferred item must use a monthly Deferred Revenue model in the same company.'))

    def write(self, values):
        if 'rental_sale_line_id' in values:
            for entry in self:
                if entry.rental_sale_line_id.id != values['rental_sale_line_id']:
                    raise UserError(_('The Rental Order source of an existing deferred item cannot be changed.'))
        return super().write(values)

    def action_validate(self):
        for entry in self.filtered('rental_sale_line_id'):
            entry.rental_sale_line_id._check_rental_posted_invoice_accounts(entry.deferred_account_id)
        return super().action_validate()


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    rental_deferred_entry_ids = fields.One2many(
        'account.deferred.entry', 'rental_sale_line_id', string='Rental Deferred Items',
        readonly=True, copy=False, context={'active_test': False},
    )
    rental_deferred_state = fields.Selection([
        ('not_created', 'Not Created'), ('draft', 'Draft'), ('running', 'Running'),
        ('closed', 'Closed'), ('cancelled', 'Cancelled'),
    ], string='Deferred Status', compute='_compute_rental_deferred_state', compute_sudo=True)

    @api.depends('rental_deferred_entry_ids', 'rental_deferred_entry_ids.state')
    def _compute_rental_deferred_state(self):
        for line in self:
            line.rental_deferred_state = line.with_context(active_test=False).rental_deferred_entry_ids[:1].state or 'not_created'

    def _rental_customer_invoice_lines(self):
        return self.invoice_lines.filtered(lambda line: line.move_id.move_type in ('out_invoice', 'out_receipt')
                                           and not line.move_id.is_et_penalty_invoice)

    def _check_rental_posted_invoice_accounts(self, account):
        wrong = self._rental_customer_invoice_lines().filtered(
            lambda line: line.move_id.state == 'posted' and line.account_id != account
        )
        if wrong:
            raise UserError(_('Posted rental invoices do not use the Deferred Account from the model: %s. '
                              'Accounting must review these invoices before contract-level deferred revenue can be created or validated.',
                              ', '.join(wrong.move_id.mapped('display_name'))))

    def _rental_deferred_account(self):
        self.ensure_one()
        self.check_access('read')
        # Narrow metadata lookup for ordinary sales users preparing invoices:
        # no deferred amounts, financial writes or wider public ACLs are granted.
        return self.sudo().with_context(active_test=False).rental_deferred_entry_ids.deferred_account_id

    def _prepare_invoice_line(self, **optional_values):
        values = super()._prepare_invoice_line(**optional_values)
        account = self._rental_deferred_account()
        if account and not self.display_type and not self.is_downpayment:
            values['account_id'] = account.id
        return values

    def _prepare_rental_deferred_values(self, model):
        self.ensure_one()
        order = self.order_id
        months = order.masa_sewa_bulan
        if months <= 0:
            raise UserError(_('Set a positive Total Months on %s before creating deferred revenue.', order.name))
        # Use the native tax engine with the full contractual quantity: this
        # respects discount and removes included taxes without multiplying a
        # line subtotal that might already reflect a rental pricing policy.
        base = self._prepare_base_line_for_taxes_computation(quantity=self.product_uom_qty * months)
        Tax = self.env['account.tax']
        Tax._add_tax_details_in_base_line(base, order.company_id)
        Tax._round_base_lines_tax_details([base], order.company_id)
        amount = base['tax_details']['total_excluded_currency']
        value = order.currency_id._convert(
            amount, order.company_id.currency_id, order.company_id, self.actual_delivery_date,
        )
        if order.company_id.currency_id.compare_amounts(value, 0) <= 0:
            raise UserError(_('Deferred Original Value must be greater than zero for Rental Order line "%s".', self.name))
        analytic = order._get_billing_engine_analytic_account(self)
        plate = self._rental_invoice_license_plate() or analytic.name or False
        return {
            'name': self.name or self.product_id.display_name,
            'deferred_type': 'revenue', 'company_id': order.company_id.id,
            'model_id': model.id, 'date': self.actual_delivery_date,
            'method_number': months, 'original_value': value,
            'analytic_distribution': self.analytic_distribution,
            'rental_sale_line_id': self.id,
            'rental_analytic_account_id': analytic.id or False,
            'rental_unit_plate_no': plate,
        }


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    rental_deferred_count = fields.Integer(compute='_compute_rental_deferred_info', compute_sudo=True)
    can_create_rental_deferred = fields.Boolean(compute='_compute_rental_deferred_info', compute_sudo=True)

    @api.depends('state', 'is_rental_order', 'top_billing', 'order_line.actual_delivery_date',
                 'order_line.display_type', 'order_line.is_downpayment', 'order_line.product_id',
                 'order_line.product_uom_qty', 'order_line.rental_deferred_entry_ids')
    def _compute_rental_deferred_info(self):
        for order in self:
            lines = order.with_context(active_test=False).order_line
            order.rental_deferred_count = len(lines.rental_deferred_entry_ids)
            order.can_create_rental_deferred = bool(
                order.is_rental_order and order.state in ('sale', 'done') and order.top_billing == 'dibelakang'
                and lines.filtered(lambda line: line.actual_delivery_date and line.product_id
                                   and not line.display_type and not line.is_downpayment
                                   and line.product_uom_qty > 0 and not line.rental_deferred_entry_ids)
            )

    def _rental_deferred_revenue_model(self):
        self.ensure_one()
        company = self.company_id
        model = company.rental_deferred_revenue_model_id
        if not model:
            models_in_company = self.env['account.deferred.model'].search([
                ('company_id', '=', company.id), ('deferred_type', '=', 'revenue'), ('active', '=', True),
            ])
            matches = models_in_company.filtered(lambda item: re.sub(r'[^a-z0-9]', '', item.name.casefold()) == 'pendapatanditerimadimuka')
            if len(matches) == 1:
                model = matches
        if not model:
            raise UserError(_('Select the Rental Deferred Revenue Model in Accounting Settings for %s. '
                              'A unique active Pendapatan Diterima Di Muka model can also be used automatically.', company.name))
        if model.company_id != company or model.deferred_type != 'revenue' or not model.active:
            raise UserError(_('The Rental Deferred Revenue Model must be an active revenue model in the Rental Order company.'))
        if model.method_period != 1:
            raise UserError(_('Rental deferred revenue uses Total Months as Duration. Use a monthly Deferred Model (Period Length = 1).'))
        return model

    def _lock_rental_deferred_orders(self):
        self._lock_billing_engine_orders()
        if self:
            # A row lock alone does not refresh a waiting transaction's
            # Repeatable Read snapshot. Advance the row version without changing
            # any field value, so Odoo retries stale concurrent create/post calls.
            self.env.cr.execute(SQL(
                'UPDATE sale_order SET write_date = write_date WHERE id IN %s', tuple(self.ids),
            ))

    def action_create_rental_deferred_revenue(self):
        self.ensure_one()
        self.check_access('write')
        # Match existing financial-record permissions; no sudo creation of
        # deferred records or journals from a sales-only account.
        if not self.env.user.has_group('account.group_account_manager'):
            raise AccessError(_('Only Accounting Administrators can create Rental Order deferred revenue.'))
        if self.company_id not in self.env.companies:
            raise AccessError(_('Select the Rental Order company before creating deferred revenue.'))
        self._lock_rental_deferred_orders()
        if not self.is_rental_order or self.state not in ('sale', 'done') or self.top_billing != 'dibelakang':
            raise UserError(_('Create Deferred Revenue is only available for confirmed Rental Orders with TOP Dibelakang.'))
        lines = self.with_context(active_test=False).order_line.filtered(
            lambda line: line.actual_delivery_date and line.product_id and not line.display_type
            and not line.is_downpayment and line.product_uom_qty > 0 and not line.rental_deferred_entry_ids
        )
        if not lines:
            raise UserError(_('No new Rental Order lines with Actual Delivery Date are available for deferred revenue.'))
        Entry = self.env['account.deferred.entry'].with_context(active_test=False)
        invoice_lines = lines._rental_customer_invoice_lines()
        if invoice_lines:
            existing = Entry.search([
                '|', ('source_move_line_id', 'in', invoice_lines.ids),
                ('source_move_line_ids', 'in', invoice_lines.ids),
            ])
            if existing:
                raise UserError(_('Invoice-based deferred items already exist for these Rental Order lines: %s. '
                                  'Review them before creating contract-level deferred revenue to avoid duplicate recognition.',
                                  ', '.join(existing.mapped('name'))))
        model = self._rental_deferred_revenue_model()
        lines._check_rental_posted_invoice_accounts(model.deferred_account_id)
        values = [line._prepare_rental_deferred_values(model) for line in lines]
        Entry.create(values)
        invoice_lines.filtered(lambda line: line.move_id.state == 'draft')._align_rental_deferred_account()
        return self.action_view_rental_deferred_revenue()

    def action_view_rental_deferred_revenue(self):
        self.ensure_one()
        self.check_access('read')
        return {
            'type': 'ir.actions.act_window', 'name': _('Rental Deferred Revenue'),
            'res_model': 'account.deferred.entry', 'view_mode': 'list,form',
            'domain': [('rental_order_id', '=', self.id)],
            'context': {'active_test': False, 'create': False, 'default_deferred_type': 'revenue'},
        }


class AccountMove(models.Model):
    _inherit = 'account.move'

    def _post(self, soft=True):
        invoices = self.filtered(lambda move: move.move_type in ('out_invoice', 'out_receipt')
                                 and not move.is_et_penalty_invoice and move.state == 'draft')
        orders = invoices.invoice_line_ids.sale_line_ids.order_id.filtered(
            lambda order: order.is_rental_order and (order.top_billing == 'dibelakang'
                          or order.with_context(active_test=False).order_line.rental_deferred_entry_ids)
        )
        if orders:
            orders._lock_rental_deferred_orders()
        invoices.invoice_line_ids._align_rental_deferred_account()
        return super()._post(soft=soft)

    def _get_deferred_eligible_lines(self):
        if self.move_type not in ('out_invoice', 'out_receipt') or self.is_et_penalty_invoice:
            return super()._get_deferred_eligible_lines()
        orders = self.invoice_line_ids.sale_line_ids.order_id.filtered(
            lambda order: order.is_rental_order and (order.top_billing == 'dibelakang'
                          or order.with_context(active_test=False).order_line.rental_deferred_entry_ids)
        )
        if orders:
            orders._lock_rental_deferred_orders()
        return super()._get_deferred_eligible_lines()

    def _get_deferred_source_lines(self):
        lines = super()._get_deferred_source_lines()
        if self.move_type not in ('out_invoice', 'out_receipt') or self.is_et_penalty_invoice:
            return lines
        # A contract-level deferred item already covers all months. Do not
        # recognize the same revenue again for its monthly/quarterly invoices.
        # Historical items still count if archived/cancelled or TOP is amended.
        managed = lines.sale_line_ids.sudo().with_context(active_test=False).filtered(
            lambda line: line.rental_deferred_entry_ids
        )
        return lines.filtered(lambda line: not (line.sale_line_ids & managed))


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    def _rental_deferred_target_account(self):
        self.ensure_one()
        if (self.display_type != 'product' or self.move_id.move_type not in ('out_invoice', 'out_receipt')
                or self.move_id.is_et_penalty_invoice or self.x_is_stamp_duty):
            return self.env['account.account']
        sources = self.sale_line_ids
        sources.check_access('read')
        managed = sources.sudo().with_context(active_test=False).filtered(lambda line: line.rental_deferred_entry_ids)
        if managed and len(managed) != len(sources):
            raise UserError(_('Separate invoice lines for rental units with and without contract-level deferred revenue.'))
        accounts = managed.rental_deferred_entry_ids.deferred_account_id
        if len(accounts) > 1:
            raise UserError(_('Separate invoice lines for rental units with different Deferred Accounts.'))
        return accounts

    def _align_rental_deferred_account(self):
        for line in self:
            account = line._rental_deferred_target_account()
            if account and line.account_id != account:
                if line.move_id.state != 'draft':
                    raise UserError(_('A posted rental invoice account cannot be changed automatically.'))
                line.write({'account_id': account.id})
