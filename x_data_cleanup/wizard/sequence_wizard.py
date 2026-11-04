import json

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from ..models.cleanup_preset import SEQUENCE_CODE_PREFIXES, SEQUENCE_CODES


class SequenceWizard(models.TransientModel):
    _name = 'x.cleanup.sequence.wizard'
    _description = 'Data Cleanup: Reset Sequence'

    only_transactions = fields.Boolean(string='Hanya sequence transaksi', default=True)
    search_text = fields.Char(string='Cari')
    line_ids = fields.One2many('x.cleanup.sequence.wizard.line', 'wizard_id', string='Sequence')
    number = fields.Integer(string='Mulai dari nomor', default=1)
    done_message = fields.Char(readonly=True)

    @api.model
    def _transaction_sequences(self):
        Sequence = self.env['ir.sequence'].sudo().with_context(active_test=False)
        domain = ['|', ('code', 'in', SEQUENCE_CODES)]
        domain += ['|'] * (len(SEQUENCE_CODE_PREFIXES) - 1)
        domain += [('code', '=like', prefix + '%') for prefix in SEQUENCE_CODE_PREFIXES]
        sequences = Sequence.search(domain)
        if 'stock.picking.type' in self.env:
            sequences |= self.env['stock.picking.type'].sudo().with_context(active_test=False).search([]).sequence_id
        if 'helpdesk.team' in self.env and 'ticket_sequence_id' in self.env['helpdesk.team']._fields:
            sequences |= self.env['helpdesk.team'].sudo().with_context(active_test=False).search([]).ticket_sequence_id
        return sequences

    @api.model
    def _reset_sequences(self, sequences, number):
        """ number_next written through the ORM: a 'standard' sequence alters its PostgreSQL sequence too """
        if number < 1:
            raise UserError(_('Nomor awal minimal 1.'))
        sequences.sudo().write({'number_next': number})
        sequences.sudo().date_range_ids.write({'number_next': number})
        return len(sequences)

    @api.model
    def action_open(self):
        self.env['x.cleanup.guard'].check_admin()
        wizard = self.create({})
        wizard._load()
        return wizard._reopen()

    def _reopen(self):
        return {'type': 'ir.actions.act_window', 'name': _('Reset Sequence'), 'res_model': self._name,
                'res_id': self.id, 'view_mode': 'form', 'views': [(False, 'form')], 'target': 'new'}

    def _load(self):
        self.ensure_one()
        if self.only_transactions:
            sequences = self._transaction_sequences()
        else:
            sequences = self.env['ir.sequence'].sudo().with_context(active_test=False).search([])
        if self.search_text:
            text = self.search_text.lower()
            sequences = sequences.filtered(lambda s: text in (s.name or '').lower() or text in (s.code or '').lower()
                                           or text in (s.prefix or '').lower())
        self.line_ids.unlink()
        self.line_ids = [fields.Command.create({
            'sequence_id': seq.id, 'selected': self.only_transactions,
        }) for seq in sequences.sorted(lambda s: (s.code or '', s.name or ''))]

    def action_load(self):
        self._load()
        return self._reopen()

    def action_select_all(self):
        self.line_ids.selected = True
        return self._reopen()

    def action_select_none(self):
        self.line_ids.selected = False
        return self._reopen()

    def action_reset(self):
        self.ensure_one()
        self.env['x.cleanup.guard'].check_unlocked()
        lines = self.line_ids.filtered('selected')
        if not lines:
            raise UserError(_('Pilih minimal satu sequence.'))
        count = self._reset_sequences(lines.sequence_id, self.number)
        self.env['x.cleanup.log'].sudo().create({
            'name': _('Reset %(count)s sequence ke %(number)s', count=count, number=self.number),
            'user_login': self.env.user.login,
            'database': self.env.cr.dbname,
            'mode': 'sequence',
            'options': json.dumps({'number': self.number}),
            'details': '\n'.join('%s [%s] %s' % (s.name, s.code or '-', s.prefix or '') for s in lines.sequence_id),
        })
        self.done_message = _('%(count)s sequence direset, nomor berikutnya %(number)s.', count=count,
                              number=self.number)
        self._load()
        return self._reopen()


class SequenceWizardLine(models.TransientModel):
    _name = 'x.cleanup.sequence.wizard.line'
    _description = 'Data Cleanup: Baris Sequence'
    _order = 'code, name'

    wizard_id = fields.Many2one('x.cleanup.sequence.wizard', required=True, ondelete='cascade')
    sequence_id = fields.Many2one('ir.sequence', required=True, ondelete='cascade')
    selected = fields.Boolean(string='Reset')
    name = fields.Char(related='sequence_id.name')
    code = fields.Char(related='sequence_id.code')
    prefix = fields.Char(related='sequence_id.prefix')
    implementation = fields.Selection(related='sequence_id.implementation')
    use_date_range = fields.Boolean(related='sequence_id.use_date_range')
    number_next_actual = fields.Integer(related='sequence_id.number_next_actual', string='Nomor Berikutnya')
