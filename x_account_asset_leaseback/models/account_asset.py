from odoo import Command, fields, models, _
from odoo.exceptions import UserError


class AccountAsset(models.Model):
    _inherit = "account.asset"

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
            # Bring depreciation up to the disposal date so the book value is current.
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
            # Use the *actual* accumulated depreciation posted up to the disposal
            # date (sum of the real depreciation moves), exactly like the native
            # ``_get_disposal_moves``. The theoretical ``_get_own_book_value`` can
            # differ from the posted board by a period rounding, which would leave
            # a non-zero remaining value on the depreciation board.
            lines_before = asset.depreciation_move_ids.filtered(
                lambda m: m.date <= disposal_date and m.asset_move_type != "sale"
            )
            depreciated_amount = currency.round(
                sum(lines_before.mapped("depreciation_value")) + asset.already_depreciated_amount_import
            )
            book_value = currency.round(original_value - depreciated_amount)
            # Positive => gain (A/R above book value) => credit deferred account.
            # Negative => loss (A/R below book value) => debit deferred account.
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
                # Loss: debit the deferred profit/loss account.
                line_ids.append(Command.create({
                    "name": name,
                    "account_id": deferred_account.id,
                    "debit": -gain_loss,
                    "credit": 0.0,
                    "analytic_distribution": analytic_distribution,
                }))
            else:
                # Gain (or break-even): credit the deferred profit/loss account.
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
            asset.write({"depreciation_move_ids": [Command.create(vals)]})
            asset.net_gain_on_sale = gain_loss
            move_ids += self.env["account.move"].search(
                [("asset_id", "=", asset.id), ("state", "=", "draft"), ("asset_move_type", "=", "sale")]
            ).ids

        return move_ids
