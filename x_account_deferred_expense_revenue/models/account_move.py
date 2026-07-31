from odoo import api, fields, models, _
from odoo.tools import float_is_zero


class AccountMove(models.Model):
    _inherit = "account.move"

    deferred_entry_ids = fields.One2many("account.deferred.entry", "source_move_id", string="Deferred Items")
    deferred_entry_count = fields.Integer(compute="_compute_deferred_entry_count")
    recognition_deferred_entry_id = fields.Many2one(
        "account.deferred.entry",
        string="Deferred Recognition Item",
        index=True,
        ondelete="restrict",
        copy=False,
    )

    def _compute_deferred_entry_count(self):
        grouped = self.env["account.deferred.entry"].read_group(
            [("source_move_id", "in", self.ids)],
            ["source_move_id"],
            ["source_move_id"],
        )
        counts = {item["source_move_id"][0]: item["source_move_id_count"] for item in grouped}
        for move in self:
            move.deferred_entry_count = counts.get(move.id, 0)

    @api.depends("state", "auto_post", "date", "recognition_deferred_entry_id")
    def _compute_hide_post_button(self):
        super()._compute_hide_post_button()
        for move in self.filtered("recognition_deferred_entry_id"):
            move.hide_post_button = True

    def _post(self, soft=True):
        posted = super()._post(soft=soft)
        if not self.env.context.get("skip_deferred_generation"):
            posted._create_deferred_entries_from_invoice_lines()
        recognition_entries = self.env["account.deferred.entry.line"].search([
            ("move_id", "in", posted.ids),
        ]).deferred_id
        if recognition_entries:
            recognition_entries._update_state_after_posting()
        return posted

    def action_create_deferred_entries(self):
        self._create_deferred_entries_from_invoice_lines()
        return self.action_view_deferred_entries()

    def action_view_deferred_entries(self):
        self.ensure_one()
        action = {
            "type": "ir.actions.act_window",
            "name": _("Deferred Items"),
            "res_model": "account.deferred.entry",
            "view_mode": "list,form",
            "domain": [("source_move_id", "=", self.id)],
            "context": {"default_source_move_id": self.id},
        }
        if self.deferred_entry_count == 1:
            action.update(
                {
                    "view_mode": "form",
                    "res_id": self.deferred_entry_ids.id,
                }
            )
        return action

    def _create_deferred_entries_from_invoice_lines(self):
        supported_move_types = ("in_invoice", "in_receipt", "out_invoice", "out_receipt")
        for move in self.filtered(lambda item: item.move_type in supported_move_types):
            for line in move.invoice_line_ids:
                account = line.account_id
                model = account.deferred_model_id
                if (
                    not model
                    or account.deferred_automation == "no"
                    or line.display_type in ("line_section", "line_note")
                    or self.env["account.deferred.entry"].search_count([("source_move_line_id", "=", line.id)])
                ):
                    continue
                if move.move_type in ("in_invoice", "in_receipt") and model.deferred_type != "expense":
                    continue
                if move.move_type in ("out_invoice", "out_receipt") and model.deferred_type != "revenue":
                    continue
                amount = abs(line.balance)
                if move.company_currency_id.is_zero(amount):
                    continue
                quantity = abs(line.quantity or 1.0)
                quantity_rounding = line.product_uom_id.rounding if line.product_uom_id else 1.0
                split_count = int(quantity) if quantity > 1 and float_is_zero(quantity - int(quantity), precision_rounding=quantity_rounding) else 1
                start_date = self.env["account.deferred.entry"].new({"model_id": model.id})._get_first_recognition_date(
                    move.invoice_date or move.date or fields.Date.context_today(self)
                )
                unit_amount = move.company_currency_id.round(amount / split_count)
                allocated = 0.0
                entries = self.env["account.deferred.entry"]
                base_name = line.name or move.name or _("Deferred Item")
                for index in range(1, split_count + 1):
                    entry_amount = unit_amount
                    if index == split_count:
                        entry_amount = amount - allocated
                    allocated += entry_amount
                    entry_name = base_name
                    if split_count > 1:
                        entry_name = _("%(name)s (%(index)s of %(total)s)") % {
                            "name": base_name,
                            "index": index,
                            "total": split_count,
                        }
                    entries |= self.env["account.deferred.entry"].create(
                        {
                            "name": entry_name,
                            "deferred_type": model.deferred_type,
                            "company_id": move.company_id.id,
                            "model_id": model.id,
                            "source_move_id": move.id,
                            "source_move_line_id": line.id,
                            "date": start_date,
                            "original_value": entry_amount,
                            "analytic_distribution": line.analytic_distribution,
                        }
                    )
                if account.deferred_automation == "validate":
                    # action_validate() already posts any periods that are
                    # already due (e.g. a bill entered in July whose board
                    # starts in April), so no extra call is needed here.
                    entries.action_validate()
