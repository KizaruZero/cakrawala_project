from odoo import api, fields, models


class FleetSPKZeroAmountWizard(models.TransientModel):
    """Confirmation before submitting an SPK whose total is Rp 0 (free service)."""

    _name = "fleet.spk.zero.amount.wizard"
    _description = "SPK Zero Amount Confirmation"

    spk_ids = fields.Many2many("fleet.spk", string="SPK", readonly=True)
    zero_spk_names = fields.Char(compute="_compute_zero_spk_names")

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        if self.env.context.get("active_model") == "fleet.spk":
            values["spk_ids"] = [(6, 0, self.env.context.get("active_ids", []))]
        return values

    @api.depends("spk_ids")
    def _compute_zero_spk_names(self):
        for wizard in self:
            wizard.zero_spk_names = ", ".join(wizard.spk_ids.filtered(lambda spk: not spk.total_amount).mapped("name"))

    def action_confirm(self):
        self.ensure_one()
        return self.spk_ids.with_context(spk_zero_amount_confirmed=True).action_submit_for_approval()
