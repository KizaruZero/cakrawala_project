from dateutil.relativedelta import relativedelta

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class AccountDeferredEntry(models.Model):
    _name = "account.deferred.entry"
    _description = "Deferred Expense / Revenue"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _check_company_auto = True
    _order = "date desc, id desc"

    name = fields.Char(required=True, tracking=True)
    deferred_type = fields.Selection(
        [("expense", "Deferred Expense"), ("revenue", "Deferred Revenue")],
        required=True,
        tracking=True,
    )
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("running", "Running"),
            ("closed", "Closed"),
            ("cancelled", "Cancelled"),
        ],
        default="draft",
        required=True,
        tracking=True,
    )
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)
    currency_id = fields.Many2one(related="company_id.currency_id")
    model_id = fields.Many2one("account.deferred.model", string="Deferred Model", required=True, check_company=True)
    source_move_id = fields.Many2one("account.move", string="Source Invoice/Bill", readonly=True, check_company=True)
    source_move_line_id = fields.Many2one("account.move.line", string="Source Invoice/Bill Line", readonly=True, check_company=True)
    date = fields.Date(string="Recognition Start Date", required=True)
    original_value = fields.Monetary(required=True)
    residual_value = fields.Monetary(compute="_compute_amounts", store=True)
    recognized_value = fields.Monetary(compute="_compute_amounts", store=True)
    method = fields.Selection(related="model_id.method", readonly=True)
    method_number = fields.Integer(related="model_id.method_number", readonly=True)
    method_period = fields.Integer(related="model_id.method_period", readonly=True)
    computation = fields.Selection(related="model_id.computation", readonly=True)
    deferred_account_id = fields.Many2one(related="model_id.deferred_account_id", readonly=True)
    recognition_account_id = fields.Many2one(related="model_id.recognition_account_id", readonly=True)
    journal_id = fields.Many2one(related="model_id.journal_id", readonly=True)
    analytic_distribution = fields.Json()
    analytic_precision = fields.Integer(default=2)
    line_ids = fields.One2many("account.deferred.entry.line", "deferred_id", string="Recognition Board")
    partner_id = fields.Many2one(
        "res.partner",
        string="Partner Link",
        compute="_compute_partner_id",
    )
    incoming_payment_ids = fields.One2many(
        "account.payment",
        "deferred_entry_id",
        string="Incoming Payments",
    )
    purchase_order_ids = fields.One2many(
        "purchase.order",
        "deferred_entry_id",
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

    @api.depends("source_move_id.partner_id")
    def _compute_partner_id(self):
        for entry in self:
            entry.partner_id = entry.source_move_id.partner_id

    @api.depends("incoming_payment_ids.name", "incoming_payment_ids.state")
    def _compute_incoming_payment_info(self):
        for entry in self:
            payment = entry.incoming_payment_ids.sorted(key="id", reverse=True)[:1]
            if payment:
                entry.incoming_payment_ref = payment.id
                entry.incoming_payment_status = payment.state
            else:
                entry.incoming_payment_ref = False
                entry.incoming_payment_status = False

    @api.depends("purchase_order_ids.name", "purchase_order_ids.state")
    def _compute_purchase_order_info(self):
        for entry in self:
            po = entry.purchase_order_ids.sorted(key="id", reverse=True)[:1]
            if po:
                entry.purchase_order_ref = po.id
                entry.purchase_order_status = po.state
            else:
                entry.purchase_order_ref = False
                entry.purchase_order_status = False

    def action_create_incoming_payment(self):
        self.ensure_one()
        if self.incoming_payment_ref:
            raise UserError(_("Incoming Payment sudah dibuat untuk deferred item ini."))

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
                "default_deferred_entry_id": self.id,
            },
        })
        return action

    def _get_purchase_order_redirect_context(self):
        self.ensure_one()
        context = {
            **self.env.context,
            "default_origin": self.name,
            "default_partner_ref": self.name,
            "default_deferred_entry_id": self.id,
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
            raise UserError(_("Purchase Order sudah dibuat untuk deferred item ini."))

        action = self.env["ir.actions.actions"]._for_xml_id("purchase.purchase_form_action")
        action.update({
            "views": [(self.env.ref("purchase.purchase_order_form").id, "form")],
            "view_mode": "form",
            "target": "current",
            "context": self._get_purchase_order_redirect_context(),
        })
        return action

    def init(self):
        self.env.cr.execute(
            "ALTER TABLE account_deferred_entry "
            "DROP CONSTRAINT IF EXISTS account_deferred_entry_source_line_unique"
        )

    @api.depends("line_ids.amount", "line_ids.state", "original_value")
    def _compute_amounts(self):
        for entry in self:
            recognized = sum(entry.line_ids.filtered(lambda line: line.state == "posted").mapped("amount"))
            entry.recognized_value = recognized
            entry.residual_value = entry.original_value - recognized

    @api.constrains("original_value")
    def _check_original_value(self):
        for entry in self:
            if entry.original_value <= 0:
                raise ValidationError(_("Original value must be greater than zero."))

    def _get_first_recognition_date(self, source_date):
        self.ensure_one()
        source_date = source_date or fields.Date.context_today(self)
        if self.model_id.first_recognition == "next_month":
            return source_date + relativedelta(day=1, months=1)
        return source_date

    def _prepare_board_lines(self):
        self.ensure_one()
        currency = self.currency_id
        amount = currency.round(self.original_value / self.method_number)
        lines = []
        allocated = 0.0
        for number in range(1, self.method_number + 1):
            line_amount = amount
            if number == self.method_number:
                line_amount = self.original_value - allocated
            allocated += line_amount
            lines.append(
                fields.Command.create(
                    {
                        "sequence": number,
                        "date": self.date + relativedelta(months=(number - 1) * self.method_period),
                        "amount": line_amount,
                    }
                )
            )
        return lines

    def action_compute_board(self):
        for entry in self:
            if entry.line_ids.filtered(lambda line: line.state == "posted"):
                raise UserError(_("You cannot recompute a board that already has posted entries."))
            entry.line_ids.mapped("move_id").filtered(lambda move: move.state != "posted").unlink()
            entry.line_ids.unlink()
            entry.line_ids = entry._prepare_board_lines()
        return True

    def _generate_moves(self):
        """Materialise the whole recognition schedule as draft journal entries.

        Like Odoo's native Assets feature, every period gets an ``account.move``
        up-front. ``action_validate`` then calls ``_post()`` on all of them:
        past/current periods are posted immediately at their accounting date and
        future periods are scheduled with ``auto_post='at_date'`` for the native
        Accounting scheduler (``account.ir_cron_auto_post_draft_entry``).
        """
        for entry in self:
            entry.line_ids._ensure_move()

    def action_validate(self):
        for entry in self:
            if not entry.line_ids:
                entry.action_compute_board()
            entry.state = "running"
        self._generate_moves()
        # Mirror native Assets validate(): post past/current periods immediately at
        # their accounting date and schedule future periods with auto_post=at_date.
        draft_moves = self.mapped("line_ids.move_id").filtered(lambda move: move.state == "draft")
        if draft_moves:
            draft_moves.with_context(skip_deferred_generation=True)._post()
        self._update_state_after_posting()
        return True

    def action_cancel(self):
        for entry in self:
            if entry.line_ids.filtered(lambda line: line.state == "posted"):
                raise UserError(_("You cannot cancel a deferred item that already has posted entries."))
            entry.line_ids.mapped("move_id").filtered(lambda move: move.state != "posted").unlink()
            entry.state = "cancelled"
        return True

    def _update_state_after_posting(self):
        for entry in self:
            if entry.state == "running" and not entry.line_ids.filtered(lambda line: line.state != "posted"):
                entry.state = "closed"

    def _get_posting_date(self, target_date):
        """Return a safe accounting date for a recognition move.

        When the recognition period is backdated into a locked period (e.g. a
        deferred item created in July whose board starts in April), posting at
        the original date would be rejected by the accounting lock date. In that
        case we roll the move forward to the first open date instead of failing.
        """
        self.ensure_one()
        lock_date = self.company_id._get_user_fiscal_lock_date(self.journal_id)
        if lock_date and target_date <= lock_date:
            return lock_date + relativedelta(days=1)
        return target_date

    def _prepare_recognition_move_vals(self, amount, date, ref):
        self.ensure_one()
        date = self._get_posting_date(date)
        if self.deferred_type == "expense":
            debit_account = self.recognition_account_id
            credit_account = self.deferred_account_id
        else:
            debit_account = self.deferred_account_id
            credit_account = self.recognition_account_id
        debit_vals = {
            "name": ref,
            "account_id": debit_account.id,
            "debit": amount,
            "credit": 0.0,
        }
        credit_vals = {
            "name": ref,
            "account_id": credit_account.id,
            "debit": 0.0,
            "credit": amount,
        }
        if self.analytic_distribution:
            debit_vals["analytic_distribution"] = self.analytic_distribution
        return {
            "move_type": "entry",
            "date": date,
            "ref": ref,
            "journal_id": self.journal_id.id,
            "company_id": self.company_id.id,
            "recognition_deferred_entry_id": self.id,
            "line_ids": [fields.Command.create(debit_vals), fields.Command.create(credit_vals)],
        }

    def action_stop_deferred(self):
        AccountMove = self.env["account.move"]
        stop_date = fields.Date.context_today(self)
        for entry in self:
            if entry.state != "running":
                continue
            remaining_lines = entry.line_ids.filtered(lambda line: line.state == "draft")
            if not remaining_lines:
                entry.state = "closed"
                continue
            # Drop the pre-generated draft moves for the remaining periods; a
            # single aggregate recognition move replaces them.
            remaining_lines.mapped("move_id").filtered(lambda move: move.state != "posted").unlink()
            amount = sum(remaining_lines.mapped("amount"))
            if entry.currency_id.is_zero(amount):
                entry.state = "closed"
                continue
            ref = _("%s: Stop Deferred") % entry.name
            move = AccountMove.with_context(skip_deferred_generation=True).create(
                entry._prepare_recognition_move_vals(amount, stop_date, ref)
            )
            move.action_post()
            remaining_lines.write({"move_id": move.id})
            entry.state = "closed"
        return True

    @api.model
    def _cron_post_due_lines(self):
        """Legacy fallback for draft moves without auto_post (pre-upgrade data).

        New validations schedule future periods with auto_post=at_date and rely on
        the native Accounting scheduler instead.
        """
        draft_moves = self.search([("state", "=", "running")]).mapped("line_ids.move_id").filtered(
            lambda move: move.state == "draft" and move.auto_post == "no" and move.date <= fields.Date.context_today(self)
        )
        if draft_moves:
            draft_moves.with_context(skip_deferred_generation=True)._post()
        self.search([("state", "=", "running")])._update_state_after_posting()

    @api.model_create_multi
    def create(self, vals_list):
        entries = super().create(vals_list)
        entries.filtered(lambda entry: not entry.line_ids).action_compute_board()
        return entries


class AccountDeferredEntryLine(models.Model):
    _name = "account.deferred.entry.line"
    _description = "Deferred Recognition Line"
    _order = "date, sequence, id"
    _check_company_auto = True

    deferred_id = fields.Many2one("account.deferred.entry", required=True, ondelete="cascade", check_company=True)
    sequence = fields.Integer(default=10)
    company_id = fields.Many2one(related="deferred_id.company_id", store=True)
    currency_id = fields.Many2one(related="deferred_id.currency_id")
    date = fields.Date(required=True)
    amount = fields.Monetary(required=True)
    move_id = fields.Many2one("account.move", readonly=True, check_company=True)
    # State follows the journal entry: a period is "posted" once its move is
    # posted (whether via the board, the scheduler, or the Journal Entries view).
    state = fields.Selection(
        [("draft", "Draft"), ("posted", "Posted")],
        compute="_compute_state",
        store=True,
        readonly=True,
    )

    @api.depends("move_id.state")
    def _compute_state(self):
        for line in self:
            line.state = "posted" if line.move_id.state == "posted" else "draft"

    def _prepare_move_vals(self):
        self.ensure_one()
        entry = self.deferred_id
        line_name = _("%s - Recognition %s") % (entry.name, self.sequence)
        return entry._prepare_recognition_move_vals(self.amount, self.date, line_name)

    def _ensure_move(self):
        """Create the draft recognition move for lines that do not have one yet."""
        AccountMove = self.env["account.move"]
        for line in self.filtered(lambda item: not item.move_id):
            move = AccountMove.with_context(skip_deferred_generation=True).create(line._prepare_move_vals())
            line.move_id = move.id
