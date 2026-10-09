from odoo import api, fields, models


class ReplacementCar(models.Model):
    _inherit = 'replacement.car'

    helpdesk_ticket_id = fields.Many2one(
        'helpdesk.ticket',
        string="Helpdesk Ticket",
        copy=False,
        ondelete='set null',
    )
    bak_id = fields.Many2one(
        'bak',
        string="BAK Reference",
        copy=False,
        ondelete='set null',
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            ticket_id = vals.get('helpdesk_ticket_id')
            if ticket_id:
                ticket = self.env['helpdesk.ticket'].browse(ticket_id)
                if ticket.exists():
                    if not vals.get('bak_id') and ticket.bak_reference_id:
                        vals['bak_id'] = ticket.bak_reference_id.id
                    if not vals.get('spk_ids') and ticket.spk_reference_id:
                        vals['spk_ids'] = [(4, ticket.spk_reference_id.id)]

            bak_id = vals.get('bak_id')
            if bak_id:
                bak = self.env['bak'].browse(bak_id)
                if bak.exists():
                    if not vals.get('helpdesk_ticket_id') and bak.helpdesk_ticket_id:
                        vals['helpdesk_ticket_id'] = bak.helpdesk_ticket_id.id
                    if not vals.get('spk_ids'):
                        spk = self.env['fleet.spk'].search([('bak_reference_id', '=', bak.id)], limit=1)
                        if spk:
                            vals['spk_ids'] = [(4, spk.id)]

            spk_cmds = vals.get('spk_ids')
            if spk_cmds:
                spk_ids = []
                for cmd in spk_cmds:
                    if isinstance(cmd, (list, tuple)):
                        if cmd[0] == 4:
                            spk_ids.append(cmd[1])
                        elif cmd[0] == 6 and len(cmd) > 2:
                            spk_ids.extend(cmd[2])
                if spk_ids:
                    spks = self.env['fleet.spk'].browse(spk_ids).exists()
                    for spk in spks:
                        if not vals.get('helpdesk_ticket_id') and spk.helpdesk_ticket_id:
                            vals['helpdesk_ticket_id'] = spk.helpdesk_ticket_id.id
                        if not vals.get('bak_id') and spk.bak_reference_id:
                            vals['bak_id'] = spk.bak_reference_id.id

        return super().create(vals_list)

    def write(self, vals):
        res = super().write(vals)
        if not self.env.context.get('skip_rc_sync'):
            if any(k in vals for k in ('helpdesk_ticket_id', 'bak_id', 'spk_ids')):
                self.with_context(skip_rc_sync=True)._sync_cross_references()
        return res

    def _sync_cross_references(self):
        for rc in self:
            vals = {}
            ticket = rc.helpdesk_ticket_id
            bak = rc.bak_id
            spks = rc.spk_ids

            if not ticket:
                if bak and bak.helpdesk_ticket_id:
                    vals['helpdesk_ticket_id'] = bak.helpdesk_ticket_id.id
                    ticket = bak.helpdesk_ticket_id
                elif spks:
                    for s in spks:
                        if s.helpdesk_ticket_id:
                            vals['helpdesk_ticket_id'] = s.helpdesk_ticket_id.id
                            ticket = s.helpdesk_ticket_id
                            break

            if not bak:
                if ticket and ticket.bak_reference_id:
                    vals['bak_id'] = ticket.bak_reference_id.id
                    bak = ticket.bak_reference_id
                elif spks:
                    for s in spks:
                        if s.bak_reference_id:
                            vals['bak_id'] = s.bak_reference_id.id
                            bak = s.bak_reference_id
                            break

            if not spks:
                spk = False
                if ticket and ticket.spk_reference_id:
                    spk = ticket.spk_reference_id
                elif bak:
                    spk = self.env['fleet.spk'].search([('bak_reference_id', '=', bak.id)], limit=1)
                if spk:
                    vals['spk_ids'] = [(4, spk.id)]

            if vals:
                rc.with_context(skip_rc_sync=True).write(vals)

