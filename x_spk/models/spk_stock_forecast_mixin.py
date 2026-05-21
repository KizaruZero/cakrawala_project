# Part of x_spk. Forecast-at-date fields aligned with sale_stock for the qty popover.
from collections import defaultdict
from datetime import timedelta

from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.tools.date_utils import end_of


class SpkStockForecastMixin(models.AbstractModel):
    _name = 'spk.stock.forecast.mixin'
    _description = 'SPK line stock forecast (quotation-style widget)'

    state = fields.Selection(
        [('draft', 'Draft'), ('sent', 'Sent'), ('sale', 'Sales Order')],
        string='Forecast UI state',
        default='draft',
        required=True,
        readonly=True,
        help='Technical field for the stock forecast popover; SPK lines use quotation (draft) mode.',
    )
    qty_delivered = fields.Float(string='Delivered quantity', default=0.0)
    customer_lead = fields.Float(compute='_compute_customer_lead')
    forecast_product_id = fields.Many2one(
        'product.product',
        string='Forecast product',
        compute='_compute_forecast_product_id',
        store=True,
    )
    virtual_available_at_date = fields.Float(
        compute='_compute_qty_at_date', digits='Product Unit',
    )
    scheduled_date = fields.Datetime(compute='_compute_qty_at_date')
    forecast_expected_date = fields.Datetime(compute='_compute_qty_at_date')
    free_qty_today = fields.Float(compute='_compute_qty_at_date', digits='Product Unit')
    qty_available_today = fields.Float(compute='_compute_qty_at_date', digits='Product Unit')
    warehouse_id = fields.Many2one(
        'stock.warehouse',
        compute='_compute_warehouse_id',
        store=True,
        help='Operations type warehouse from SPK «Goods Issue Source» when set; '
             'if empty, forecast quantities use company-wide internal stock.',
    )
    qty_to_deliver = fields.Float(compute='_compute_qty_to_deliver', digits='Product Unit')
    is_mto = fields.Boolean(compute='_compute_is_mto')
    display_qty_widget = fields.Boolean(compute='_compute_qty_to_deliver')
    is_storable = fields.Boolean(compute='_compute_is_storable')

    @api.depends('product_id')
    def _compute_forecast_product_id(self):
        for line in self:
            line.forecast_product_id = False
            if line._name == 'spk.sparepart.line':
                tmpl = line.product_id
                if not tmpl or len(tmpl.product_variant_ids) != 1:
                    continue
                line.forecast_product_id = tmpl.product_variant_ids[0]
            elif line._name == 'spk.on.risk.product.line':
                line.forecast_product_id = line.product_id

    @api.depends('forecast_product_id', 'forecast_product_id.product_tmpl_id.sale_delay')
    def _compute_customer_lead(self):
        for line in self:
            variant = line.forecast_product_id
            line.customer_lead = variant.product_tmpl_id.sale_delay if variant else 0.0

    @api.depends('forecast_product_id')
    def _compute_is_storable(self):
        for line in self:
            p = line.forecast_product_id
            line.is_storable = bool(p and p.is_storable)

    @api.depends('spk_id', 'spk_id.goods_issue_source_id.warehouse_id')
    def _compute_warehouse_id(self):
        """Only scope to a warehouse when SPK sets Goods Issue Source.

        If we picked a random default warehouse, the popover would show that warehouse only
        while an unscoped view uses company-wide internal stock.
        """
        for line in self:
            wh = False
            src = line.spk_id.goods_issue_source_id
            if src and src.warehouse_id:
                wh = src.warehouse_id
            line.warehouse_id = wh

    def _spk_scheduled_datetime(self):
        self.ensure_one()
        commitment = False
        if self.spk_id and self.spk_id.spk_date:
            commitment = end_of(
                fields.Datetime.to_datetime(self.spk_id.spk_date),
                'day',
            )
        return commitment or fields.Datetime.now() + timedelta(
            days=self.customer_lead or 0.0,
        )

    @api.depends(
        'forecast_product_id',
        'quantity',
        'qty_delivered',
        'state',
        'product_uom_id',
    )
    def _compute_qty_to_deliver(self):
        for line in self:
            line.qty_to_deliver = line.quantity - line.qty_delivered
            if (
                line.state in ('draft', 'sent', 'sale')
                and line.forecast_product_id
                and line.forecast_product_id.is_storable
                and line.product_uom_id
                and line.qty_to_deliver > 0
            ):
                line.display_qty_widget = True
            else:
                line.display_qty_widget = False

    def _read_forecast_qties(self, products, date, wh_id):
        ctx = {'to_date': date}
        if wh_id:
            ctx['warehouse_id'] = wh_id
        return products.with_context(**ctx).read([
            'qty_available',
            'free_qty',
            'virtual_available',
        ])

    @api.depends(
        'forecast_product_id',
        'quantity',
        'product_uom_id',
        'spk_id.spk_date',
        'warehouse_id',
        'customer_lead',
        'display_qty_widget',
    )
    def _compute_qty_at_date(self):
        """Draft/sent quotation path from sale_stock (no sale-line moves)."""
        treated = self.browse()
        grouped_lines = defaultdict(lambda: self.browse())
        for line in self.filtered(lambda l: l.state in ('draft', 'sent')):
            if not (line.forecast_product_id and line.display_qty_widget):
                continue
            wh_id = line.warehouse_id.id if line.warehouse_id else False
            scheduled = line._spk_scheduled_datetime()
            grouped_lines[(wh_id, scheduled)] |= line

        qty_processed_per_product = defaultdict(float)
        for (wh_id, scheduled_date), lines in grouped_lines.items():
            products = lines.forecast_product_id
            product_qties = lines._read_forecast_qties(products, scheduled_date, wh_id)
            qties_per_product = {
                row['id']: (
                    row['qty_available'],
                    row['free_qty'],
                    row['virtual_available'],
                )
                for row in product_qties
            }
            for line in lines:
                line.scheduled_date = scheduled_date
                pid = line.forecast_product_id.id
                qty_available_today, free_qty_today, virtual_available_at_date = qties_per_product[pid]
                line.qty_available_today = qty_available_today - qty_processed_per_product[pid]
                line.free_qty_today = free_qty_today - qty_processed_per_product[pid]
                line.virtual_available_at_date = (
                    virtual_available_at_date - qty_processed_per_product[pid]
                )
                line.forecast_expected_date = False
                product_qty = line.quantity
                uom_line = line.product_uom_id
                product = line.forecast_product_id
                if uom_line and product.uom_id and uom_line != product.uom_id:
                    line.qty_available_today = product.uom_id._compute_quantity(
                        line.qty_available_today, uom_line,
                    )
                    line.free_qty_today = product.uom_id._compute_quantity(
                        line.free_qty_today, uom_line,
                    )
                    line.virtual_available_at_date = product.uom_id._compute_quantity(
                        line.virtual_available_at_date, uom_line,
                    )
                    product_qty = uom_line._compute_quantity(
                        product_qty, product.uom_id,
                    )
                qty_processed_per_product[pid] += product_qty
            treated |= lines

        remaining = self - treated
        remaining.virtual_available_at_date = False
        remaining.scheduled_date = False
        remaining.forecast_expected_date = False
        remaining.free_qty_today = False
        remaining.qty_available_today = False

    @api.depends(
        'forecast_product_id',
        'forecast_product_id.route_ids',
        'forecast_product_id.categ_id.total_route_ids',
        'warehouse_id',
        'display_qty_widget',
    )
    def _compute_is_mto(self):
        self.is_mto = False
        for line in self:
            if not line.display_qty_widget:
                continue
            product = line.forecast_product_id
            if not product:
                continue
            product_routes = product.route_ids + product.categ_id.total_route_ids
            mto_route = line.warehouse_id.mto_pull_id.route_id if line.warehouse_id else False
            if not mto_route:
                try:
                    mto_route = self.env['stock.warehouse']._find_or_create_global_route(
                        'stock.route_warehouse0_mto',
                        _('Replenish on Order (MTO)'),
                        create=False,
                    )
                except UserError:
                    mto_route = False
            if mto_route and mto_route in product_routes:
                line.is_mto = True
