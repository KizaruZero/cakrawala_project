from collections import OrderedDict

from odoo import fields, models, tools


class SPKServiceReportLine(models.Model):
    _name = "spk.service.report.line"
    _description = "SPK Service Report Detail"
    _auto = False
    _rec_name = "product_id"
    _order = "spk_date desc, spk_id desc, line_id asc"

    line_id = fields.Many2one("spk.product.line", string="SPK Product Line", readonly=True)
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
    description = fields.Text(string="Keterangan SPK", readonly=True)
    line_description = fields.Text(string="Keterangan Line", readonly=True)
    currency_id = fields.Many2one("res.currency", string="Currency", readonly=True)

    product_id = fields.Many2one("product.product", string="Product", readonly=True)
    product_name = fields.Char(string="Product Name", readonly=True)
    product_category_id = fields.Many2one("product.category", string="Product Category", readonly=True)
    product_uom_id = fields.Many2one("uom.uom", string="UoM", readonly=True)
    quantity = fields.Float(string="Qty", readonly=True)
    unit_price = fields.Monetary(string="Harga", currency_field="currency_id", readonly=True)
    subtotal_without_tax = fields.Monetary(string="Subtotal Before Tax", currency_field="currency_id", readonly=True)
    subtotal_sparepart = fields.Monetary(string="Subtotal Sparepart", currency_field="currency_id", readonly=True)
    subtotal_service = fields.Monetary(string="Subtotal Service", currency_field="currency_id", readonly=True)
    subtotal_on_risk = fields.Monetary(string="Subtotal On Risk", currency_field="currency_id", readonly=True)
    ppn_total = fields.Monetary(string="PPN (Rp.)", currency_field="currency_id", readonly=True)
    product_total = fields.Monetary(string="Sub Total Sparepart", currency_field="currency_id", readonly=True)
    service_total = fields.Monetary(string="Sub Total Service", currency_field="currency_id", readonly=True)
    total = fields.Monetary(string="Total", currency_field="currency_id", readonly=True)
    is_service_line = fields.Boolean(string="Is Service", readonly=True)
    is_on_risk = fields.Boolean(string="On Risk", readonly=True)
    line_type = fields.Selection(
        [
            ("sparepart", "Sparepart"),
            ("service", "Service"),
            ("on_risk", "On Risk"),
        ],
        string="Line Type",
        readonly=True,
    )

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(
            """
            CREATE OR REPLACE VIEW %s AS (
                SELECT
                    l.id AS id,
                    l.id AS line_id,
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
                    l.description AS line_description,
                    s.currency_id AS currency_id,
                    l.product_id AS product_id,
                    COALESCE(pt.name->>'id_ID', pt.name->>'en_US', pt.name::text) AS product_name,
                    pt.categ_id AS product_category_id,
                    l.product_uom_id AS product_uom_id,
                    l.quantity AS quantity,
                    l.unit_price AS unit_price,
                    COALESCE(l.subtotal_without_tax, 0.0) AS subtotal_without_tax,
                    CASE
                        WHEN NOT COALESCE(pt.is_on_risk, false) AND NOT l.is_service_line
                            THEN COALESCE(l.subtotal_without_tax, 0.0)
                        ELSE 0.0
                    END AS subtotal_sparepart,
                    CASE
                        WHEN NOT COALESCE(pt.is_on_risk, false) AND l.is_service_line
                            THEN COALESCE(l.subtotal_without_tax, 0.0)
                        ELSE 0.0
                    END AS subtotal_service,
                    CASE
                        WHEN COALESCE(pt.is_on_risk, false)
                            THEN COALESCE(l.subtotal_without_tax, 0.0)
                        ELSE 0.0
                    END AS subtotal_on_risk,
                    COALESCE(l.tax_total, 0.0) AS ppn_total,
                    CASE WHEN NOT l.is_service_line THEN COALESCE(l.subtotal, 0.0) ELSE 0.0 END AS product_total,
                    CASE WHEN l.is_service_line THEN COALESCE(l.subtotal, 0.0) ELSE 0.0 END AS service_total,
                    COALESCE(l.subtotal, 0.0) AS total,
                    l.is_service_line AS is_service_line,
                    COALESCE(pt.is_on_risk, false) AS is_on_risk,
                    CASE
                        WHEN COALESCE(pt.is_on_risk, false) THEN 'on_risk'
                        WHEN l.is_service_line THEN 'service'
                        ELSE 'sparepart'
                    END AS line_type
                FROM spk_product_line l
                JOIN fleet_spk s ON s.id = l.spk_id
                LEFT JOIN res_partner rp ON rp.id = s.vendor_id
                LEFT JOIN product_product pp ON pp.id = l.product_id
                LEFT JOIN product_template pt ON pt.id = pp.product_tmpl_id
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

    def _format_report_amount(self, amount):
        return "Rp %s" % "{:,.2f}".format(amount or 0.0)

    def _format_report_number(self, amount):
        return "{:,.0f}".format(amount or 0.0)

    def _format_report_date(self, value):
        return value.strftime("%d-%b-%y").upper() if value else ""

    def _get_print_groups(self):
        groups = OrderedDict()
        sorted_lines = self.sorted(
            key=lambda line: (
                line.spk_date and line.spk_date.isoformat() or "",
                line.spk_number or "",
                line.line_id.id or line.id,
            )
        )
        for line in sorted_lines:
            key = line.spk_id.id or line.id
            if key not in groups:
                groups[key] = {
                    "record": line,
                    "lines": self.env[self._name],
                    "sparepart_total": 0.0,
                    "service_total": 0.0,
                    "on_risk_total": 0.0,
                    "ppn_total": 0.0,
                    "grand_total": 0.0,
                }
            group = groups[key]
            group["lines"] |= line
            group["sparepart_total"] += line.subtotal_sparepart or 0.0
            group["service_total"] += line.subtotal_service or 0.0
            group["on_risk_total"] += line.subtotal_on_risk or 0.0
            group["ppn_total"] += line.ppn_total or 0.0
            group["grand_total"] += line.total or 0.0

        result = []
        for group in groups.values():
            group["rowspan"] = max(len(group["lines"]), 1)
            result.append(group)
        return result
