from odoo import models, fields, tools

class POReportView(models.Model):
    _name = 'po.report.view'
    _description = 'Purchase Order Custom Report'
    _auto = False

    order_id = fields.Many2one('purchase.order', string='Purchase Order', readonly=True)
    po_number = fields.Char(string='Purchase Order Number', readonly=True)
    po_date = fields.Datetime(string='PO Date', readonly=True)
    vendor_id = fields.Many2one('res.partner', string='Vendor (Dealer)', readonly=True)
    leasing_id = fields.Many2one('res.partner', string='Leasing', readonly=True)
    customer_id = fields.Many2one('res.partner', string='Customer', readonly=True)
    so_reference = fields.Char(string='SO Reference', readonly=True)
    state = fields.Selection([
        ('draft', 'RFQ'),
        ('waiting_approval', 'Waiting Approval'),
        ('sent', 'RFQ Sent'),
        ('to approve', 'To Approve'),
        ('purchase', 'Purchase Order'),
        ('done', 'Locked'),
        ('cancel', 'Cancelled'),
        ('rejected', 'Rejected')
    ], string='Status', readonly=True)
    scheduled_date = fields.Datetime(string='TGL Permohonan Delivery', readonly=True)
    
    product_id = fields.Many2one('product.product', string='Type Kendaraan', readonly=True)
    model_year = fields.Char(string='Tahun', readonly=True)
    color = fields.Char(string='Warna', readonly=True)
    plate_number = fields.Char(string='Plate Number', readonly=True)
    effective_date = fields.Datetime(string='TGL Terima Dari Dealer', readonly=True)
    
    aging_req_vs_terima = fields.Integer(string='Aging Delivery (Tgl Req Deliv - Tgl Terima)', readonly=True)
    aging_po_vs_terima = fields.Integer(string='Aging Delivery (Tgl PO - Tgl Terima)', readonly=True)
    
    otr_awal = fields.Float(string='OTR Awal', readonly=True)
    fixed_disc = fields.Float(string='Fixed Disc', readonly=True)
    percent_disc = fields.Float(string='% Disc', readonly=True)
    total_amount = fields.Float(string='Total Amount', readonly=True)
    down_payment = fields.Float(string='Down Payment', readonly=True)
    currency_id = fields.Many2one('res.currency', string='Currency', readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW %s AS (
                SELECT
                    (ROW_NUMBER() OVER ())::INTEGER as id,
                    po.id as order_id,
                    po.name as po_number,
                    po.state as state,
                    po.date_order as po_date,
                    po.partner_id as vendor_id,
                    po.leasing_partner_id as leasing_id,
                    po.currency_id as currency_id,
                    so.partner_id as customer_id,
                    so.name as so_reference,
                    sp.scheduled_date as scheduled_date,
                    pol.product_id as product_id,
                    COALESCE(vy.name, fv.model_year) as model_year,
                    COALESCE(vc.name, fv.color) as color,
                    sml.initial_license_plate as plate_number,
                    sp.date_done as effective_date,
                    
                    GREATEST(0, EXTRACT(DAY FROM (sp.date_done - sp.scheduled_date))::INTEGER) as aging_req_vs_terima,
                    GREATEST(0, EXTRACT(DAY FROM (sp.date_done - po.date_order))::INTEGER) as aging_po_vs_terima,

                    pol.price_unit as otr_awal,
                    (COALESCE(pol.fixed_discount, 0.0) / NULLIF(pol.product_qty, 0)) as fixed_disc,
                    pol.discount as percent_disc,
                    
                    -- Prorata Total Amount (per 1 qty, menggunakan price_subtotal untaxed)
                    (pol.price_subtotal / NULLIF(pol.product_qty, 0)) as total_amount,

                    -- Prorata Down Payment (berdasarkan proporsi nilai 1 qty terhadap total PO)
                    COALESCE(dp.amount, 0.0) * ((pol.price_total / NULLIF(pol.product_qty, 0)) / NULLIF(po.amount_total, 0)) as down_payment

                FROM purchase_order po
                LEFT JOIN purchase_order_line pol ON pol.order_id = po.id
                LEFT JOIN sale_order so ON po.sale_order_id = so.id
                LEFT JOIN stock_move sm ON sm.purchase_line_id = pol.id AND sm.state != 'cancel'
                LEFT JOIN stock_move_line sml ON sml.move_id = sm.id
                LEFT JOIN stock_picking sp ON sm.picking_id = sp.id
                LEFT JOIN stock_picking_type spt ON sp.picking_type_id = spt.id AND spt.code = 'incoming'
                LEFT JOIN stock_lot lot ON sml.lot_id = lot.id
                LEFT JOIN fleet_vehicle fv ON fv.asset_number = lot.name
                LEFT JOIN vehicle_year vy ON sml.vehicle_year_id = vy.id
                LEFT JOIN vehicle_color vc ON sml.vehicle_color_id = vc.id
                
                -- Subquery: Total DP dari Posted Vendor Bill
                LEFT JOIN (
                    SELECT 
                        dp_pol.order_id, 
                        SUM(
                            CASE 
                                WHEN am.move_type = 'in_invoice' AND aml.price_total > 0 THEN aml.price_total 
                                WHEN am.move_type = 'in_refund' AND aml.price_total > 0 THEN -aml.price_total 
                                ELSE 0 
                            END
                        ) as amount
                    FROM purchase_order_line dp_pol
                    JOIN account_move_line aml ON aml.purchase_line_id = dp_pol.id
                    JOIN account_move am ON aml.move_id = am.id
                    WHERE dp_pol.is_downpayment = TRUE
                      AND am.state = 'posted'
                      AND am.move_type IN ('in_invoice', 'in_refund')
                    GROUP BY dp_pol.order_id
                ) dp ON dp.order_id = po.id
                
                WHERE COALESCE(pol.is_downpayment, FALSE) = FALSE 
                  AND pol.display_type IS NULL
            )
        """ % (self._table,))
