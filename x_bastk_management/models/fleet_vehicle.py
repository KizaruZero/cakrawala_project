from lxml import etree

from odoo import fields, models, api, _
from odoo.exceptions import UserError

# Fields that move a locked vehicle out of its inactive status: Fleet
# Administrators only.
FLEET_LOCK_REOPEN_FIELDS = {'state_id', 'fleet_sub_status_id', 'active'}


class FleetVehicle(models.Model):
    _inherit = 'fleet.vehicle'

    engine_number = fields.Char(string='Engine Number', tracking=True)
    bastk_count = fields.Integer(compute='_compute_bastk_count', string='BASTK Count')
    asset_type_id = fields.Many2one('bastk.asset.type', string='Asset Type', tracking=True)

    is_fleet_locked = fields.Boolean(
        string='Read-only (Inactive Status)',
        compute='_compute_is_fleet_locked',
        help='The vehicle is in a status flagged "Is Inactive State" (e.g. Sold): '
             'it can no longer be edited.',
    )
    can_reopen_fleet = fields.Boolean(compute='_compute_can_reopen_fleet')

    @api.depends('state_id.is_inactive_state', 'fleet_sub_status_id.state_id.is_inactive_state')
    def _compute_is_fleet_locked(self):
        for vehicle in self:
            vehicle.is_fleet_locked = bool(
                vehicle.state_id.is_inactive_state
                or vehicle.fleet_sub_status_id.state_id.is_inactive_state
            )

    @api.depends_context('uid')
    def _compute_can_reopen_fleet(self):
        self.can_reopen_fleet = self._can_reopen_fleet()

    def _can_reopen_fleet(self):
        return self.env.su or self.env.user.has_group('fleet.fleet_group_manager')

    @api.model
    def _fleet_lock_free_field(self, name):
        """Fields that stay writable on a locked vehicle: its chatter."""
        return name.startswith(('message_', 'activity_', 'website_message_'))

    def write(self, vals):
        locked = self.filtered('is_fleet_locked')
        if locked:
            blocked = {name for name in vals if not self._fleet_lock_free_field(name)}
            if self._can_reopen_fleet():
                blocked -= FLEET_LOCK_REOPEN_FIELDS
            if blocked:
                raise UserError(_(
                    "Fleet %(vehicles)s is in an inactive status (%(state)s) and is read-only.\n"
                    "Fields refused: %(fields)s.",
                    vehicles=', '.join(locked.mapped('display_name')),
                    state=', '.join(set(locked.mapped('state_id.name'))),
                    fields=', '.join(sorted(self._fields[name].string for name in blocked if name in self._fields)),
                ))
        return super().write(vals)

    @api.ondelete(at_uninstall=False)
    def _unlink_except_fleet_locked(self):
        locked = self.filtered('is_fleet_locked')
        if locked:
            raise UserError(_(
                "Fleet %s is in an inactive status and cannot be deleted.",
                ', '.join(locked.mapped('display_name')),
            ))

    @api.model
    def _get_view(self, view_id=None, view_type='form', **options):
        """Lock the whole vehicle form while the vehicle is in an inactive status.

        Done on the final arch so the fields added by every fleet module are
        covered. Fields of embedded one2many lists are left alone: making the
        one2many field itself read-only already locks its lines.
        """
        arch, view = super()._get_view(view_id, view_type, **options)
        if view_type == 'form':
            for node in arch.iter('field'):
                name = node.get('name')
                if name in ('is_fleet_locked', 'can_reopen_fleet') or any(
                        parent.tag == 'field' for parent in node.iterancestors()):
                    continue
                lock = 'is_fleet_locked'
                if name in FLEET_LOCK_REOPEN_FIELDS:
                    lock = 'is_fleet_locked and not can_reopen_fleet'
                readonly = (node.get('readonly') or '').strip()
                if readonly in ('1', 'True', 'true'):
                    continue
                node.set('readonly', '(%s) or (%s)' % (readonly, lock) if readonly and readonly not in ('0', 'False', 'false') else lock)
            sheet = arch.find('.//sheet')
            if sheet is not None:
                sheet.insert(0, etree.fromstring(
                    '<div class="alert alert-warning mb-2" role="alert" invisible="not is_fleet_locked">'
                    '<field name="is_fleet_locked" invisible="1"/><field name="can_reopen_fleet" invisible="1"/>'
                    '<strong>Read-only:</strong> this fleet is in an inactive status (e.g. Sold) and can no longer be edited.'
                    '</div>'
                ))
        return arch, view

    def _compute_bastk_count(self):
        for vehicle in self:
            vehicle.bastk_count = self.env['bastk.management'].search_count([('vehicle_id', '=', vehicle.id)])

    def action_view_bastk(self):
        self.ensure_one()
        return {
            'name': 'BASTK',
            'view_mode': 'list,form',
            'res_model': 'bastk.management',
            'type': 'ir.actions.act_window',
            'domain': [('vehicle_id', '=', self.id)],
            'context': {'default_vehicle_id': self.id},
        }

class FleetVehicleState(models.Model):
    _inherit = 'fleet.vehicle.state'

    is_inactive_state = fields.Boolean(string="Is Inactive State", default=False)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('is_inactive_state'):
                self.search([('is_inactive_state', '=', True)]).write({'is_inactive_state': False})
        return super().create(vals_list)

    def write(self, vals):
        if vals.get('is_inactive_state'):
            self.search([('is_inactive_state', '=', True), ('id', '!=', self.id)]).write({'is_inactive_state': False})
        return super().write(vals)
