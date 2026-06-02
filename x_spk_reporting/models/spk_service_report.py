from odoo import fields, models, tools


class SPKServiceReport(models.Model):
    _name = "spk.service.report"
    _description = "SPK Service Report"
    _auto = False
    _rec_name = "spk_number"
    _order = "spk_date desc, spk_id desc"

    spk_id = fields.Many2one("fleet.spk", string="SPK", readonly=True)
    spk_date = fields.Date(string="Tgl Service", readonly=True)
    spk_number = fields.Char(string="No SPK", readonly=True)
    category = fields.Selection(
        [
            ("internal", "Internal"),
            ("external", "External"),
        ],
        string="Category",
        readonly=True,
    )
    vendor_id = fields.Many2one("res.partner", string="Vendor", readonly=True)
    vendor_name = fields.Char(string="Nama Bengkel", readonly=True)
    jenis = fields.Char(string="Jns", readonly=True)
    odometer = fields.Float(string="KM", readonly=True, aggregator=None)
    description = fields.Text(string="Keterangan", readonly=True)
    currency_id = fields.Many2one("res.currency", string="Currency", readonly=True)

    sparepart_total = fields.Monetary(string="SparePart (Rp.)", currency_field="currency_id", readonly=True)
    ppn_total = fields.Monetary(string="PPN (Rp.)", currency_field="currency_id", readonly=True)
    service_total = fields.Monetary(string="Jasa (Rp.)", currency_field="currency_id", readonly=True)
    grand_total = fields.Monetary(string="Total (Rp.)", currency_field="currency_id", readonly=True)

    sparepart_summary = fields.Text(string="Spare Part", readonly=True)
    service_summary = fields.Text(string="Service", readonly=True)
    product_line_summary = fields.Text(string="Product Line", readonly=True)
    has_sparepart = fields.Boolean(string="Has Sparepart", readonly=True)
    has_service = fields.Boolean(string="Has Service", readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(
            """
            CREATE OR REPLACE VIEW %s AS (
                SELECT
                    s.id AS id,
                    s.id AS spk_id,
                    s.spk_date AS spk_date,
                    s.name AS spk_number,
                    s.category AS category,
                    s.vendor_id AS vendor_id,
                    CASE
                        WHEN s.category = 'external' THEN COALESCE(rp.name, s.vendor_name)
                        ELSE COALESCE(s.vendor_name, rp.name)
                    END AS vendor_name,
                    'REGULER'::varchar AS jenis,
                    s.odometer AS odometer,
                    s.description AS description,
                    s.currency_id AS currency_id,
                    COALESCE(line_totals.sparepart_total, 0.0) AS sparepart_total,
                    COALESCE(line_totals.ppn_total, 0.0) AS ppn_total,
                    COALESCE(line_totals.service_total, 0.0) AS service_total,
                    COALESCE(line_totals.grand_total, 0.0) AS grand_total,
                    COALESCE(line_totals.sparepart_summary, '') AS sparepart_summary,
                    COALESCE(line_totals.service_summary, '') AS service_summary,
                    COALESCE(line_totals.product_line_summary, '') AS product_line_summary,
                    COALESCE(line_totals.has_sparepart, false) AS has_sparepart,
                    COALESCE(line_totals.has_service, false) AS has_service
                FROM fleet_spk s
                LEFT JOIN res_partner rp ON rp.id = s.vendor_id
                LEFT JOIN (
                    SELECT
                        l.spk_id,
                        SUM(CASE WHEN NOT l.is_service_line THEN l.subtotal ELSE 0 END) AS sparepart_total,
                        SUM(COALESCE(l.tax_total, 0.0)) AS ppn_total,
                        SUM(CASE WHEN l.is_service_line THEN l.subtotal ELSE 0 END) AS service_total,
                        SUM(COALESCE(l.subtotal, 0.0)) AS grand_total,
                        STRING_AGG(
                            CASE WHEN NOT l.is_service_line
                                THEN CONCAT_WS(' ', COALESCE(pt.name->>'id_ID', pt.name->>'en_US', pt.name::text), '(' || TRIM(TRAILING '.' FROM TRIM(TRAILING '0' FROM l.quantity::text)) || ')')
                            END,
                            ', ' ORDER BY l.id
                        ) AS sparepart_summary,
                        STRING_AGG(
                            CASE WHEN l.is_service_line
                                THEN CONCAT_WS(' ', COALESCE(pt.name->>'id_ID', pt.name->>'en_US', pt.name::text), '(' || TRIM(TRAILING '.' FROM TRIM(TRAILING '0' FROM l.quantity::text)) || ')')
                            END,
                            ', ' ORDER BY l.id
                        ) AS service_summary,
                        STRING_AGG(
                            CONCAT_WS(' ', COALESCE(pt.name->>'id_ID', pt.name->>'en_US', pt.name::text), '(' || TRIM(TRAILING '.' FROM TRIM(TRAILING '0' FROM l.quantity::text)) || ')'),
                            ', ' ORDER BY l.id
                        ) AS product_line_summary,
                        BOOL_OR(NOT l.is_service_line) AS has_sparepart,
                        BOOL_OR(l.is_service_line) AS has_service
                    FROM spk_product_line l
                    LEFT JOIN product_product pp ON pp.id = l.product_id
                    LEFT JOIN product_template pt ON pt.id = pp.product_tmpl_id
                    GROUP BY l.spk_id
                ) line_totals ON line_totals.spk_id = s.id
            )
            """
            % self._table
        )

    def action_open_spk(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": self.spk_number,
            "res_model": "fleet.spk",
            "res_id": self.spk_id.id,
            "view_mode": "form",
            "target": "current",
        }

    def _get_sparepart_lines(self):
        self.ensure_one()
        return self.spk_id.product_line_ids.filtered(lambda line: not line.is_service_line)

    def _get_service_lines(self):
        self.ensure_one()
        return self.spk_id.product_line_ids.filtered(lambda line: line.is_service_line)

    def _format_report_amount(self, amount):
        return "Rp %s" % "{:,.2f}".format(amount or 0.0)
