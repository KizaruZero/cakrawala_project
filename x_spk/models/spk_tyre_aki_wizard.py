from odoo import models, fields


class SPKTyreAKIWizard(models.TransientModel):
    _name = "spk.tyre.aki.wizard"
    _description = "SPK Tyre/AKI Detail Notification Wizard"

    spk_id = fields.Many2one("fleet.spk", string="SPK", readonly=True)
    
    # Tyre fields
    tyre_detail_ids = fields.One2many(
        "spk.tyre.aki.wizard.tyre",
        "wizard_id",
        string="Tyre Details to Fill",
    )
    
    # AKI fields
    aki_detail_ids = fields.One2many(
        "spk.tyre.aki.wizard.aki",
        "wizard_id",
        string="AKI Details to Fill",
    )
    
    message = fields.Html(string="Message", readonly=True)

    def action_ok(self):
        """Close warning wizard."""
        return {"type": "ir.actions.act_window_close"}


class SPKTyreAKIWizardTyre(models.TransientModel):
    _name = "spk.tyre.aki.wizard.tyre"
    _description = "SPK Tyre Detail - Wizard"

    wizard_id = fields.Many2one("spk.tyre.aki.wizard", ondelete="cascade")
    tyre_line_id = fields.Many2one("spk.tyre.line", string="Tyre Detail Line", readonly=True)
    product_description = fields.Text(string="Product Description", readonly=True)
    old_production_number = fields.Char(string="Old Production Number")
    new_production_number = fields.Char(string="New Production Number")
    notes = fields.Text(string="Notes")


class SPKTyreAKIWizardAKI(models.TransientModel):
    _name = "spk.tyre.aki.wizard.aki"
    _description = "SPK AKI Detail - Wizard"

    wizard_id = fields.Many2one("spk.tyre.aki.wizard", ondelete="cascade")
    aki_line_id = fields.Many2one("spk.aki.line", string="AKI Detail Line", readonly=True)
    product_description = fields.Text(string="Product Description", readonly=True)
    old_AKI_code = fields.Char(string="Old AKI Code")
    new_AKI_code = fields.Char(string="New AKI Code")
    notes = fields.Text(string="Notes")
