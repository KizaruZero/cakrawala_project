from odoo import api, fields, models, _
from odoo.tools import float_is_zero


class AccountMove(models.Model):
    _inherit = "account.move"

    deferred_entry_ids = fields.One2many("account.deferred.entry", "source_move_id", string="Deferred Items")
    deferred_entry_count = fields.Integer(compute="_compute_deferred_entry_count")
    deferred_merge = fields.Boolean(
        string="Merge Deferred Items",
        help="Group invoice lines sharing the same account and analytic distribution into a single deferred item.",
    )
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

    def _get_deferred_eligible_lines(self):
        self.ensure_one()
        already_deferred = self.env["account.deferred.entry"].search([
            "|",
            ("source_move_line_id", "in", self.invoice_line_ids.ids),
            ("source_move_line_ids", "in", self.invoice_line_ids.ids),
        ])
        done_lines = already_deferred.source_move_line_id | already_deferred.source_move_line_ids
        expected_type = "expense" if self.move_type in ("in_invoice", "in_receipt") else "revenue"
        return self.invoice_line_ids.filtered(
            lambda line: line.account_id.deferred_model_id
            and line.account_id.deferred_automation != "no"
            and line.display_type not in ("line_section", "line_note")
            and line.account_id.deferred_model_id.deferred_type == expected_type
            and line not in done_lines
        )

    def _get_deferred_merge_name(self, lines):
        """Name a merged deferred item after the line labels minus the product suffix.

        Document bills label lines as ``<document> - <product>``; the merged item
        keeps only ``<document>``. Distinct prefixes in one group are joined.
        """
        self.ensure_one()
        prefixes = []
        for line in lines:
            name = line.name or ""
            suffix = f" - {line.product_id.name}" if line.product_id else ""
            if suffix and name.endswith(suffix):
                name = name[: -len(suffix)]
            if name and name not in prefixes:
                prefixes.append(name)
        return ", ".join(prefixes) or self.name or _("Deferred Item")

    def _create_deferred_entries(self, lines, base_name, split_count=1):
        """Create the deferred item(s) for ``lines``, which share one account."""
        self.ensure_one()
        account = lines.account_id
        model = account.deferred_model_id
        amount = abs(sum(lines.mapped("balance")))
        if self.company_currency_id.is_zero(amount):
            return
        start_date = self.env["account.deferred.entry"].new({"model_id": model.id})._get_first_recognition_date(
            self.invoice_date or self.date or fields.Date.context_today(self)
        )
        unit_amount = self.company_currency_id.round(amount / split_count)
        allocated = 0.0
        entries = self.env["account.deferred.entry"]
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
                    "company_id": self.company_id.id,
                    "model_id": model.id,
                    "source_move_id": self.id,
                    "source_move_line_id": lines[0].id,
                    "source_move_line_ids": [fields.Command.set(lines.ids)],
                    "date": start_date,
                    "original_value": entry_amount,
                    "analytic_distribution": lines[0].analytic_distribution,
                }
            )
        if account.deferred_automation == "validate":
            entries.action_validate()

    def _create_deferred_entries_from_invoice_lines(self):
        supported_move_types = ("in_invoice", "in_receipt", "out_invoice", "out_receipt")
        for move in self.filtered(lambda item: item.move_type in supported_move_types):
            eligible_lines = move._get_deferred_eligible_lines()
            if move.deferred_merge:
                groups = {}
                for line in eligible_lines:
                    analytic_key = tuple(sorted((line.analytic_distribution or {}).items()))
                    key = (line.account_id.id, analytic_key)
                    groups[key] = groups.get(key, self.env["account.move.line"]) | line
                for lines in groups.values():
                    move._create_deferred_entries(lines, move._get_deferred_merge_name(lines))
                continue
            for line in eligible_lines:
                quantity = abs(line.quantity or 1.0)
                quantity_rounding = line.product_uom_id.rounding if line.product_uom_id else 1.0
                split_count = int(quantity) if quantity > 1 and float_is_zero(quantity - int(quantity), precision_rounding=quantity_rounding) else 1
                move._create_deferred_entries(line, line.name or move.name or _("Deferred Item"), split_count)
