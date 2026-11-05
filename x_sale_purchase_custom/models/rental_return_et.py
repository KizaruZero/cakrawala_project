from odoo import Command, _, api, fields, models
from odoo.exceptions import UserError


class SaleOrderETLine(models.Model):
    _name = 'sale.order.et.line'
    _description = 'Rental Order Early Termination Line'
    _order = 'sequence, id'

    sequence = fields.Integer(default=10)
    name = fields.Char(string='ET Reference', required=True, copy=False, readonly=True, default='ET-01')
    order_id = fields.Many2one(
        'sale.order', string='Rental Order', required=True, ondelete='cascade', index=True
    )
    company_id = fields.Many2one(related='order_id.company_id', store=True)
    currency_id = fields.Many2one(related='order_id.currency_id', store=True)
    termination_date = fields.Date(
        string='Termination Date', default=fields.Date.context_today, required=True
    )
    sale_line_ids = fields.Many2many(
        'sale.order.line',
        'sale_order_et_line_sol_rel',
        'et_line_id',
        'sale_line_id',
        string='Return ET Units',
        readonly=True,
        copy=False,
        check_company=True,
    )
    unit_summary = fields.Char(
        string='Units', compute='_compute_unit_summary', store=True
    )
    return_picking_ids = fields.Many2many(
        'stock.picking',
        'sale_order_et_line_picking_rel',
        'et_line_id',
        'picking_id',
        string='Return ET Pickings',
        readonly=True,
        copy=False,
        check_company=True,
    )
    penalty_amount = fields.Monetary(
        string='Penalty Amount', currency_field='currency_id', default=0.0
    )
    reason = fields.Text(string='Reason for Early Termination')
    notes = fields.Text(string='Additional Notes')
    state = fields.Selection(
        selection=[
            ('pending', 'Waiting Approval'),
            ('approved', 'Approved'),
            ('invoiced', 'Invoiced'),
        ],
        string='Status',
        default='pending',
        required=True,
        copy=False,
    )
    approved_by = fields.Many2one('res.users', string='Approved By', readonly=True, copy=False)
    approval_date = fields.Datetime(string='Approval Date', readonly=True, copy=False)
    is_delegated = fields.Boolean(string='Approved by Delegation', readonly=True, copy=False)
    delegator_id = fields.Many2one('res.users', string='Delegated by Director', readonly=True, copy=False)
    invoice_id = fields.Many2one('account.move', string='Penalty Invoice', readonly=True, copy=False)
    can_approve_et = fields.Boolean(
        string='Can Approve ET', compute='_compute_can_approve_et'
    )

    @api.depends('sale_line_ids', 'sale_line_ids.product_id', 'sale_line_ids.fleet_vehicle_id')
    def _compute_unit_summary(self):
        for et_line in self:
            labels = []
            for sline in et_line.sale_line_ids:
                plate = (
                    sline._rental_invoice_license_plate()
                    if hasattr(sline, '_rental_invoice_license_plate')
                    else False
                )
                product_name = sline.product_id.display_name or sline.name or ''
                if plate:
                    labels.append(f"{plate} ({product_name})" if product_name else plate)
                elif product_name:
                    labels.append(product_name)
            et_line.unit_summary = ', '.join(labels) if labels else False

    def _compute_can_approve_et(self):
        current_user = self.env.user
        is_allowed = (
            self.env.is_superuser()
            or current_user.has_group('x_sale_purchase_custom.group_et_director')
            or self.env['et.approval.delegation'].is_user_et_delegate(current_user)
        )
        for et_line in self:
            et_line.can_approve_et = is_allowed

    def write(self, vals):
        editable_before_approve = {'termination_date', 'penalty_amount', 'reason', 'notes'}
        if not self.env.context.get('_et_system_update') and editable_before_approve.intersection(vals):
            for rec in self:
                if rec.state != 'pending':
                    raise UserError(_(
                        'Data Early Termination (%s) yang sudah disetujui tidak dapat diubah kembali.',
                        rec.name,
                    ))
        res = super().write(vals)
        if not self.env.context.get('_et_system_update') and editable_before_approve.intersection(vals):
            for rec in self:
                if rec.order_id and rec == rec.order_id.et_line_ids[-1:]:
                    rec.order_id.sudo().write({
                        'et_termination_date': rec.termination_date,
                        'et_penalty_amount': rec.penalty_amount,
                        'et_reason': rec.reason,
                        'et_notes': rec.notes,
                    })
        return res

    def action_approve(self):
        self.ensure_one()
        current_user = self.env.user
        is_super = self.env.is_superuser()
        is_director = current_user.has_group('x_sale_purchase_custom.group_et_director')
        delegation = self.env['et.approval.delegation'].get_active_et_delegation(current_user)
        is_delegate = bool(delegation)

        if not (is_super or is_director or is_delegate):
            raise UserError(_('Hanya Direktur atau Delegasi Direktur yang aktif yang dapat menyetujui Early Termination.'))
        if self.state != 'pending':
            raise UserError(_('Early Termination (%s) sudah disetujui sebelumnya.', self.name))
        if self.penalty_amount <= 0:
            raise UserError(_('Nominal Penalty Amount harus lebih dari 0 untuk disetujui.'))

        approval_now = fields.Datetime.now()
        line_vals = {
            'state': 'approved',
            'approved_by': current_user.id,
            'approval_date': approval_now,
        }
        order_vals = {
            'et_is_approved': True,
            'et_approved_by': current_user.id,
            'et_approval_date': approval_now,
            'et_penalty_amount': self.penalty_amount,
            'et_termination_date': self.termination_date,
        }
        if not is_director and is_delegate:
            delegator_id = delegation.delegator_user_id.id if delegation.delegator_user_id else False
            line_vals.update({'is_delegated': True, 'delegator_id': delegator_id})
            order_vals.update({'et_is_delegated': True, 'et_delegator_id': delegator_id})

        self.sudo().with_context(_et_system_update=True).write(line_vals)
        self.order_id.sudo().write(order_vals)

        formatted_amount = (
            self.currency_id.format(self.penalty_amount)
            if self.currency_id
            else str(self.penalty_amount)
        )
        if not is_director and is_delegate:
            delegator_name = delegation.delegator_user_id.name if delegation.delegator_user_id else "Direktur"
            approver_info = f"Delegasi Direktur ({current_user.name}), didelegasikan oleh {delegator_name}"
        else:
            approver_info = f"Direktur ({current_user.name})"

        self.order_id.sudo().message_post(body=_(
            "Early Termination <b>%s</b> (%s) telah disetujui oleh %s dengan nilai penalti %s. "
            "Silakan klik tombol <b>Create Invoice</b> pada baris terkait untuk membuat Draft Invoice Penalti.",
            self.name,
            self.unit_summary or '-',
            approver_info,
            formatted_amount,
        ))
        return True

    def action_open_create_invoice_warning(self):
        self.ensure_one()
        if self.state == 'pending':
            raise UserError(_('Silakan lakukan Approve terlebih dahulu sebelum membuat Invoice Penalti.'))
        if self.invoice_id or self.state == 'invoiced':
            raise UserError(_('Invoice Penalti untuk %s sudah dibuat.', self.name))

        wizard = self.env['et.create.invoice.warning.wizard'].create({
            'et_line_id': self.id,
        })
        return {
            'name': _('Peringatan Create Invoice Early Termination'),
            'type': 'ir.actions.act_window',
            'res_model': 'et.create.invoice.warning.wizard',
            'res_id': wizard.id,
            'view_mode': 'form',
            'views': [(self.env.ref('x_sale_purchase_custom.view_et_create_invoice_warning_wizard_form').id, 'form')],
            'target': 'new',
        }

    def _create_penalty_invoice(self):
        self.ensure_one()
        if self.state == 'pending':
            raise UserError(_('Silakan lakukan Approve terlebih dahulu sebelum membuat Invoice Penalti.'))
        if self.invoice_id:
            raise UserError(_('Invoice Penalti untuk %s sudah dibuat.', self.name))

        invoice = self.order_id.sudo()._create_et_penalty_invoice(
            penalty_amount=self.penalty_amount,
            et_reference=self.name,
            unit_summary=self.unit_summary,
        )
        self.sudo().with_context(_et_system_update=True).write({
            'invoice_id': invoice.id,
            'state': 'invoiced',
        })
        self.order_id.sudo().write({'et_invoice_id': invoice.id})

        formatted_amount = (
            self.currency_id.format(self.penalty_amount)
            if self.currency_id
            else str(self.penalty_amount)
        )
        self.order_id.sudo().message_post(body=_(
            "Draft Invoice Penalti untuk Early Termination <b>%s</b> (%s) berhasil dibuat: %s sebesar %s.",
            self.name,
            self.unit_summary or '-',
            invoice._get_html_link(),
            formatted_amount,
        ))

        return {
            'name': _('Penalty Invoice'),
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'res_id': invoice.id,
            'view_mode': 'form',
            'target': 'current',
        }


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    et_return_line_ids = fields.Many2many(
        'sale.order.line', 'sale_order_et_return_line_rel', 'order_id', 'line_id',
        string='Return ET Units', readonly=True, copy=False, check_company=True,
    )
    et_return_picking_ids = fields.Many2many(
        'stock.picking', 'sale_order_et_return_picking_rel', 'order_id', 'picking_id',
        string='Return ET Pickings', readonly=True, copy=False, check_company=True,
    )

    def _check_return_et_request_allowed(self):
        self.ensure_one()
        if not self.is_rental_order or self.state not in ('sale', 'done'):
            raise UserError(_('Return ET is only available for confirmed Rental Orders.'))

    def _get_return_et_eligible_lines(self):
        self.ensure_one()
        eligible = self.env['sale.order.line']
        for line in self.order_line:
            if line.display_type or line.is_downpayment or line.qty_delivered <= 0 or line.qty_returned > 0:
                continue
            has_active_et_move = any(
                move.is_rental_return_et and move.state != 'cancel'
                for move in line.move_ids
            )
            if has_active_et_move or line.qty_returned_et > 0:
                if self._get_return_et_move_quantities(line):
                    eligible |= line
            elif line.qty_returned_et == 0:
                eligible |= line
        return eligible

    def _get_return_et_move_quantities(self, line):
        """Completed deliveries less all non-cancelled return reservations."""
        self.ensure_one()
        result = []
        for move in line.move_ids.sorted('id'):
            if (move.state != 'done' or move.scrap_id or move.location_dest_id.usage != 'customer'
                    or not move.picking_id or move.picking_id.company_id != self.company_id):
                continue
            returned = sum(
                returned.product_uom._compute_quantity(returned.product_uom_qty, move.product_uom)
                for returned in move.returned_move_ids if returned.state != 'cancel'
            )
            quantity = move.product_uom._compute_quantity(max(move.quantity - returned, 0), line.product_uom_id)
            if quantity > 0:
                result.append((move, quantity))
        return result

    def _return_et_penalty_amount(self, lines):
        self.ensure_one()
        # Use the actual unit's sale line, never just its product or a blank /
        # reused plate string. Grouped invoices contribute only selected units.
        rows = self.billing_engine_line_ids.filtered(lambda row: (
            row.sale_line_id in lines and (
                not row.invoice_id or row.invoice_id.state == 'draft'
                or row.invoice_id.state == 'posted' and row.invoice_id.payment_state == 'not_paid'
            )
        ))
        return self.currency_id.round(sum(rows.mapped('amount')) * 0.25)

    def _register_return_et_request(self, lines, pickings):
        self.ensure_one()
        penalty = self._return_et_penalty_amount(lines)
        today = fields.Date.context_today(self)
        seq_no = len(self.et_line_ids) + 1
        is_legacy_pending = (
            self.is_early_termination_requested
            and not self.et_line_ids
            and not self.et_return_picking_ids
            and not self.et_is_approved
        )
        et_line = self.env['sale.order.et.line'].create({
            'order_id': self.id,
            'sequence': seq_no * 10,
            'name': f"ET-{seq_no:02d}",
            'termination_date': (
                self.et_termination_date
                if is_legacy_pending and self.et_termination_date
                else today
            ),
            'sale_line_ids': [Command.set(lines.ids)],
            'return_picking_ids': [Command.set(pickings.ids)],
            'penalty_amount': penalty,
            'reason': self.et_reason if is_legacy_pending else False,
            'notes': self.et_notes if is_legacy_pending else False,
        })
        all_lines = self.et_line_ids.sale_line_ids
        all_pickings = self.et_line_ids.return_picking_ids
        self.write({
            'is_early_termination_requested': True,
            'et_return_line_ids': [Command.set(all_lines.ids)],
            'et_return_picking_ids': [Command.set(all_pickings.ids)],
            'et_penalty_amount': et_line.penalty_amount,
            'et_termination_date': et_line.termination_date,
        })
        return et_line


class StockMove(models.Model):
    _inherit = 'stock.move'

    is_rental_return_et = fields.Boolean(string='Return ET', readonly=True, copy=False, index=True)

    @api.model_create_multi
    def create(self, vals_list):
        if any(values.get('is_rental_return_et') for values in vals_list):
            raise UserError(_('Return ET classification is managed by the Return ET wizard.'))
        return super().create(vals_list)

    def write(self, values):
        if 'is_rental_return_et' in values:
            raise UserError(_('Return ET classification cannot be changed manually.'))
        return super().write(values)

    def _mark_rental_return_et(self):
        if any(move.state in ('done', 'cancel') or not move.origin_returned_move_id
               or not move.sale_line_id.order_id.is_rental_order for move in self):
            raise UserError(_('Only new Rental Order return moves can be marked as Return ET.'))
        super(StockMove, self).write({'is_rental_return_et': True})

    def _action_done(self, cancel_backorder=False):
        result = super()._action_done(cancel_backorder=cancel_backorder)
        lines = self.filtered('is_rental_return_et').sale_line_id
        if lines:
            # Run after native rental counters: ET must not also fill Returned.
            for name in ('qty_delivered', 'qty_returned', 'qty_returned_et'):
                self.env.add_to_compute(lines._fields[name], lines)
            lines._recompute_recordset(['qty_delivered', 'qty_returned', 'qty_returned_et'])

        # Auto-fill Return Date (bastk_return_date) on rental order lines for validated return moves
        return_moves = self.filtered(
            lambda m: m.sale_line_id.order_id.is_rental_order
            and m.location_id.usage == 'customer'
            and m.location_dest_id.usage == 'internal'
            and not m.scrap_id
        )
        for move in return_moves:
            line = move.sale_line_id
            if line and not line.bastk_return_date:
                et_line = line.order_id.et_line_ids.filtered(
                    lambda et: move.picking_id in et.return_picking_ids or line in et.sale_line_ids
                )
                if et_line and et_line[-1].termination_date:
                    line.bastk_return_date = et_line[-1].termination_date
                else:
                    ref_dt = move.picking_id.date_done or move.date or fields.Datetime.now()
                    line.bastk_return_date = fields.Datetime.context_timestamp(move, ref_dt).date()
        return result

    def _create_backorder(self):
        et_sources = {
            (move.origin_returned_move_id.id, move.sale_line_id.id)
            for move in self if move.is_rental_return_et
        }
        result = super()._create_backorder()
        remaining_et = result.filtered(lambda move: (
            move.origin_returned_move_id.id, move.sale_line_id.id,
        ) in et_sources)
        if remaining_et:
            remaining_et._mark_rental_return_et()
        return result
