from odoo import Command, api, fields, models, _
from odoo.exceptions import UserError


class AccountAsset(models.Model):
    _inherit = "account.asset"

    partner_id = fields.Many2one(
        "res.partner",
        string="Partner Link",
        compute="_compute_partner_id",
    )
    incoming_payment_ids = fields.One2many(
        "account.payment",
        "asset_id",
        string="Incoming Payments",
    )
    purchase_order_ids = fields.One2many(
        "purchase.order",
        "asset_id",
        string="Purchase Orders",
    )
    incoming_payment_ref = fields.Many2one(
        "account.payment",
        string="Incoming Payment Reference",
        compute="_compute_incoming_payment_info",
        store=True,
        tracking=True,
    )
    incoming_payment_status = fields.Selection(
        [
            ("draft", "Draft"),
            ("in_process", "In Process"),
            ("paid", "Paid"),
            ("canceled", "Canceled"),
            ("rejected", "Rejected"),
        ],
        string="Incoming Payment Status",
        compute="_compute_incoming_payment_info",
        store=True,
        tracking=True,
    )
    purchase_order_ref = fields.Many2one(
        "purchase.order",
        string="Purchase Order Reference",
        compute="_compute_purchase_order_info",
        store=True,
        tracking=True,
    )
    purchase_order_status = fields.Selection(
        [
            ("draft", "RFQ"),
            ("waiting_approval", "Waiting Approval"),
            ("sent", "RFQ Sent"),
            ("to approve", "To Approve"),
            ("purchase", "Purchase Order"),
            ("done", "Locked"),
            ("cancel", "Cancelled"),
            ("rejected", "Rejected"),
        ],
        string="Purchase Order Status",
        compute="_compute_purchase_order_info",
        store=True,
        tracking=True,
    )
    leaseback_deferred_pl_amount = fields.Monetary(
        string="Deferred Profit/Loss",
        currency_field="currency_id",
        default=0.0,
        readonly=True,
        tracking=True,
        help="Nilai selisih laba/rugi ditangguhkan dari transaksi leaseback.",
    )

    @api.depends("original_move_line_ids.move_id.partner_id")
    def _compute_partner_id(self):
        for rec in self:
            partner = self.env["res.partner"]
            if rec.original_move_line_ids:
                partners = rec.original_move_line_ids.mapped("move_id.partner_id")
                if partners:
                    partner = partners[0]
            rec.partner_id = partner

    @api.depends("incoming_payment_ids.name", "incoming_payment_ids.state")
    def _compute_incoming_payment_info(self):
        for rec in self:
            payment = rec.incoming_payment_ids.sorted(key="id", reverse=True)[:1]
            if payment:
                rec.incoming_payment_ref = payment.id
                rec.incoming_payment_status = payment.state
            else:
                rec.incoming_payment_ref = False
                rec.incoming_payment_status = False

    @api.depends("purchase_order_ids.name", "purchase_order_ids.state")
    def _compute_purchase_order_info(self):
        for rec in self:
            po = rec.purchase_order_ids.sorted(key="id", reverse=True)[:1]
            if po:
                rec.purchase_order_ref = po.id
                rec.purchase_order_status = po.state
            else:
                rec.purchase_order_ref = False
                rec.purchase_order_status = False

    def action_create_incoming_payment(self):
        self.ensure_one()
        if self.incoming_payment_ref:
            raise UserError(_("Incoming Payment sudah dibuat untuk aset ini."))

        action = self.env["ir.actions.actions"]._for_xml_id("account.action_account_payments")
        action.update({
            "views": [(self.env.ref("account.view_account_payment_form").id, "form")],
            "view_mode": "form",
            "target": "current",
            "context": {
                **self.env.context,
                "default_payment_type": "inbound",
                "default_partner_type": "customer",
                "default_partner_id": self.partner_id.id if self.partner_id else False,
                "default_asset_id": self.id,
            },
        })
        return action

    def _get_purchase_order_redirect_context(self):
        self.ensure_one()
        context = {
            **self.env.context,
            "default_origin": self.name,
            "default_partner_ref": self.name,
            "default_asset_id": self.id,
        }
        if self.partner_id:
            context["default_partner_id"] = self.partner_id.id

        po_model = self.env["purchase.order"]
        if "purchase_order_type_master_id" in po_model._fields:
            po_type = (
                self.env["purchase.order.type.master"].search([("state", "=", "active")], limit=1)
                or self.env["purchase.order.type.master"].search([], limit=1)
            )
            if po_type:
                context["default_purchase_order_type_master_id"] = po_type.id
        if "department_id" in po_model._fields:
            department = self.env["hr.department"].search([], limit=1)
            if department:
                context["default_department_id"] = department.id
        return context

    def action_create_purchase_order(self):
        self.ensure_one()
        if self.purchase_order_ref:
            raise UserError(_("Purchase Order sudah dibuat untuk aset ini."))

        action = self.env["ir.actions.actions"]._for_xml_id("purchase.purchase_form_action")
        action.update({
            "views": [(self.env.ref("purchase.purchase_order_form").id, "form")],
            "view_mode": "form",
            "target": "current",
            "context": self._get_purchase_order_redirect_context(),
        })
        return action

    def set_to_close_leaseback(self, ar_account, ar_amount, deferred_account, date=None, message=None):
        """Close an asset through a leaseback (a Sell without an invoice).

        Mirrors the native ``set_to_close`` flow used by Sell/Dispose but the
        proceeds come from a manual A/R amount instead of a customer invoice,
        and the gain/loss versus the book value is booked to a single deferred
        profit/loss account.
        """
        self.ensure_one()
        disposal_date = date or fields.Date.today()
        if disposal_date <= self.company_id._get_user_fiscal_lock_date(self.journal_id):
            raise UserError(_("You cannot process a leaseback before the lock date."))
        if self.children_ids.filtered(lambda a: a.state in ("draft", "open") or a.value_residual > 0):
            raise UserError(_(
                "You cannot automate the journal entry for an asset that has a "
                "running gross increase. Please 'Dispose' the increase(s) first."
            ))

        self.state = "close"
        move_ids = self._get_leaseback_moves(ar_account, ar_amount, deferred_account, disposal_date)
        self.message_post(body=_("Asset leased back. %s", message if message else ""))

        if move_ids:
            return {
                "name": _("Leaseback Move"),
                "view_mode": "form",
                "res_model": "account.move",
                "type": "ir.actions.act_window",
                "target": "current",
                "res_id": move_ids[0],
                "domain": [("id", "in", move_ids)],
            }

    def _get_leaseback_moves(self, ar_account, ar_amount, deferred_account, disposal_date):
        """Create the leaseback disposal move for every asset in ``self``.

        Journal (positive asset, following the Leaseback specification):

            Cr  Asset account            original value
            Dr  Accumulated Depreciation depreciated to date
            Dr  A/R Account              A/R Amount
            Cr/Dr Deferred Profit/Loss   gain -> credit, loss -> debit
        """
        move_ids = []
        for asset in self:
            asset._create_move_before_date(disposal_date)

            currency = asset.currency_id
            analytic_distribution = asset.analytic_distribution
            name = _("%(asset)s: Leaseback", asset=asset.name)

            original_value = asset.original_value
            initial_account = (
                asset.original_move_line_ids.account_id
                if len(asset.original_move_line_ids.account_id) == 1
                else asset.account_asset_id
            )
            lines_before = asset.depreciation_move_ids.filtered(
                lambda m: m.date <= disposal_date and m.asset_move_type != "sale"
            )
            depreciated_amount = currency.round(
                sum(lines_before.mapped("depreciation_value")) + asset.already_depreciated_amount_import
            )
            book_value = currency.round(original_value - depreciated_amount)
            gain_loss = currency.round(ar_amount - book_value)

            line_ids = [
                Command.create({
                    "name": name,
                    "account_id": initial_account.id,
                    "debit": 0.0,
                    "credit": original_value,
                    "analytic_distribution": analytic_distribution,
                }),
                Command.create({
                    "name": name,
                    "account_id": asset.account_depreciation_id.id,
                    "debit": depreciated_amount,
                    "credit": 0.0,
                    "analytic_distribution": analytic_distribution,
                }),
                Command.create({
                    "name": name,
                    "account_id": ar_account.id,
                    "debit": ar_amount,
                    "credit": 0.0,
                }),
            ]
            if currency.compare_amounts(gain_loss, 0) < 0:
                line_ids.append(Command.create({
                    "name": name,
                    "account_id": deferred_account.id,
                    "debit": -gain_loss,
                    "credit": 0.0,
                    "analytic_distribution": analytic_distribution,
                }))
            else:
                line_ids.append(Command.create({
                    "name": name,
                    "account_id": deferred_account.id,
                    "debit": 0.0,
                    "credit": gain_loss,
                    "analytic_distribution": analytic_distribution,
                }))

            vals = {
                "asset_id": asset.id,
                "ref": name,
                "asset_depreciation_beginning_date": disposal_date,
                "date": disposal_date,
                "journal_id": asset.journal_id.id,
                "move_type": "entry",
                "asset_move_type": "sale",
                "line_ids": line_ids,
            }
            asset.write({
                "depreciation_move_ids": [Command.create(vals)],
                "leaseback_deferred_pl_amount": gain_loss,
            })
            asset.net_gain_on_sale = gain_loss
            move_ids += self.env["account.move"].search(
                [("asset_id", "=", asset.id), ("state", "=", "draft"), ("asset_move_type", "=", "sale")]
            ).ids

        return move_ids
