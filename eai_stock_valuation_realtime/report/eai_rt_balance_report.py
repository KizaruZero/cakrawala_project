from odoo import fields, models, tools


class EaiRtBalanceReport(models.Model):
    """Saldo terbuka akun interim valuasi real-time per dokumen asal.

    * Stock Input  : PO yang sudah ditagih tetapi belum Diterima (persediaan dalam perjalanan)
                     atau Diterima tetapi belum ditagih (saldo kredit).
    * Stock Output : DO yang belum diinvoice final (barang terkirim belum ditagih).
    * Klaim Retur  : retur ke vendor yang belum ditutup credit note.
    Hanya baris dengan saldo tidak nol yang ditampilkan.
    """
    _name = 'eai.rt.balance.report'
    _description = 'Saldo Akun Interim Valuasi Real-time'
    _auto = False
    _order = 'date_first, origin_ref'

    company_id = fields.Many2one('res.company', 'Perusahaan', readonly=True)
    currency_id = fields.Many2one('res.currency', related='company_id.currency_id', readonly=True)
    role = fields.Selection([
        ('input', 'Stock Input (dalam perjalanan)'),
        ('output', 'Stock Output (terkirim belum ditagih)'),
        ('claim', 'Piutang Klaim Retur'),
    ], string='Jenis', readonly=True)
    account_id = fields.Many2one('account.account', 'Akun', readonly=True)
    origin_ref = fields.Char('Dokumen Asal', readonly=True)
    partner_id = fields.Many2one('res.partner', 'Partner', readonly=True)
    product_id = fields.Many2one('product.product', 'Produk', readonly=True)
    warehouse_id = fields.Many2one('stock.warehouse', 'Gudang/Butik', readonly=True)
    quantity = fields.Float('Qty (saldo)', readonly=True)
    balance = fields.Monetary('Saldo', currency_field='currency_id', readonly=True)
    date_first = fields.Date('Tanggal Pertama', readonly=True)
    date_last = fields.Date('Tanggal Terakhir', readonly=True)
    age_days = fields.Integer('Umur (hari)', readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(f"""
            CREATE OR REPLACE VIEW {self._table} AS (
                SELECT
                    MIN(aml.id) AS id,
                    aml.company_id,
                    aml.eai_rt_role AS role,
                    aml.account_id,
                    aml.eai_rt_origin_ref AS origin_ref,
                    aml.partner_id,
                    aml.product_id,
                    aml.eai_rt_warehouse_id AS warehouse_id,
                    SUM(SIGN(aml.balance) * ABS(COALESCE(aml.quantity, 0))) AS quantity,
                    SUM(aml.balance) AS balance,
                    MIN(aml.date) AS date_first,
                    MAX(aml.date) AS date_last,
                    (CURRENT_DATE - MIN(aml.date))::integer AS age_days
                FROM account_move_line aml
                WHERE aml.parent_state = 'posted'
                  AND aml.eai_rt_role IN ('input', 'output', 'claim')
                GROUP BY aml.company_id, aml.eai_rt_role, aml.account_id, aml.eai_rt_origin_ref,
                         aml.partner_id, aml.product_id, aml.eai_rt_warehouse_id
                HAVING ROUND(SUM(aml.balance), 2) <> 0
            )
        """)
