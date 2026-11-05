from lxml import etree

from odoo import fields, models, api, _
from odoo.exceptions import UserError

# Fields that move a locked vehicle out of its Sold status: through an Excel import
# by a Fleet Administrator only.
FLEET_LOCK_STATUS_FIELDS = {'state_id', 'fleet_sub_status_id'}


def lock_form_arch(model, arch, message):
    """Make a form read-only while `is_fleet_locked` is set, with `message` on top.

    Done on the final arch so the fields added by every module are covered. Fields of
    embedded one2many lists are left alone: making the one2many field itself read-only
    already locks its lines.
    """
    for node in arch.iter('field'):
        if node.get('name') == 'is_fleet_locked' or any(
                parent.tag == 'field' for parent in node.iterancestors()):
            continue
        readonly = (node.get('readonly') or '').strip()
        if readonly in ('1', 'True', 'true'):
            continue
        # The attribute overrides the field definition: adding one would make it editable while unlocked.
        field = model._fields.get(node.get('name'))
        if not readonly and field is not None and field.readonly:
            continue
        node.set('readonly', '(%s) or is_fleet_locked' % readonly
                 if readonly and readonly not in ('0', 'False', 'false') else 'is_fleet_locked')
    alert = etree.fromstring(
        '<div class="alert alert-warning mb-2" role="alert" invisible="not is_fleet_locked">'
        '<field name="is_fleet_locked" invisible="1"/><strong>Read-only:</strong> <span/></div>'
    )
    alert.find('span').text = message
    sheet = arch.find('.//sheet')
    (sheet if sheet is not None else arch).insert(0, alert)
    # Workflow buttons go too; print and smart buttons stay. Write checks still apply to whatever is left.
    for button in arch.iter('button'):
        invisible = (button.get('invisible') or '').strip()
        if button.get('type') != 'object' or 'print' in (button.get('name') or '') \
                or 'oe_stat_button' in (button.get('class') or '') \
                or invisible in ('1', 'True', 'true') \
                or any(parent.tag == 'field' for parent in button.iterancestors()):
            continue
        button.set('invisible', '(%s) or is_fleet_locked' % invisible if invisible else 'is_fleet_locked')


class FleetVehicle(models.Model):
    _inherit = 'fleet.vehicle'

    engine_number = fields.Char(string='Engine Number', tracking=True)
    bastk_count = fields.Integer(compute='_compute_bastk_count', string='BASTK Count')
    bastk_ids = fields.One2many('bastk.management', 'vehicle_id', string='BASTK')
    last_customer_id = fields.Many2one(
        'res.partner',
        string='Customer',
        compute='_compute_last_customer_id',
        store=True,
        help='Partner of the latest BASTK of this vehicle, whatever its state.',
    )
    show_customer = fields.Boolean(related='state_id.show_customer')
    last_bastk_id = fields.Many2one('bastk.management', string='Latest BASTK', compute='_compute_last_bastk_id')
    last_bastk_state = fields.Selection(related='last_bastk_id.state', string='Latest BASTK Status')
    asset_type_id = fields.Many2one('bastk.asset.type', string='Asset Type', tracking=True)

    is_fleet_locked = fields.Boolean(
        string='Read-only (Sold)',
        compute='_compute_is_fleet_locked',
        help='The vehicle has a sub-status flagged "Is Sold": it can no longer be edited.',
    )

    @api.depends('fleet_sub_status_id.is_sold')
    def _compute_is_fleet_locked(self):
        for vehicle in self:
            vehicle.is_fleet_locked = vehicle.fleet_sub_status_id.is_sold

    def _can_import_fleet_status(self):
        return self.env.context.get('import_file') and self.env.user.has_group('fleet.fleet_group_manager')

    @api.model
    def _fleet_lock_free_field(self, name):
        """Fields that stay writable on a locked vehicle: its chatter. An import also sends the id."""
        return name == 'id' or name.startswith(('message_', 'activity_', 'website_message_'))

    def write(self, vals):
        locked = self.filtered('is_fleet_locked')
        if locked:
            blocked = {name for name in vals if not self._fleet_lock_free_field(name)}
            if self._can_import_fleet_status():
                blocked -= FLEET_LOCK_STATUS_FIELDS
            # Automated flows may set the status the vehicle already has.
            blocked -= {name for name in blocked & FLEET_LOCK_STATUS_FIELDS
                        if all(vehicle[name].id == vals[name] for vehicle in locked)}
            if blocked:
                raise UserError(_(
                    "Fleet %(vehicles)s is %(status)s and is read-only.\n"
                    "Fields refused: %(fields)s.\n"
                    "A status changed by mistake can be corrected by a Fleet Administrator "
                    "through Export and Import.",
                    vehicles=', '.join(locked.mapped('display_name')),
                    status=', '.join(set(locked.mapped('fleet_sub_status_id.name'))),
                    fields=', '.join(sorted(self._fields[name].string for name in blocked if name in self._fields)),
                ))
        return super().write(vals)

    @api.ondelete(at_uninstall=False)
    def _unlink_except_fleet_locked(self):
        locked = self.filtered('is_fleet_locked')
        if locked:
            raise UserError(_(
                "Fleet %s is Sold and cannot be deleted.",
                ', '.join(locked.mapped('display_name')),
            ))

    @api.model
    def _get_view(self, view_id=None, view_type='form', **options):
        """Lock the whole vehicle form while the vehicle is Sold."""
        arch, view = super()._get_view(view_id, view_type, **options)
        if view_type == 'form':
            lock_form_arch(self, arch, _('this fleet is Sold and can no longer be edited.'))
        return arch, view

    @api.depends('bastk_ids.partner_id', 'bastk_ids.active')
    def _compute_last_customer_id(self):
        for vehicle in self:
            vehicle.last_customer_id = vehicle.bastk_ids.sorted('id', reverse=True)[:1].partner_id

    @api.depends('bastk_ids.state')
    def _compute_last_bastk_id(self):
        for vehicle in self:
            vehicle.last_bastk_id = vehicle.bastk_ids.sorted('id', reverse=True)[:1]

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
    show_customer = fields.Boolean(
        string='Show Customer',
        help='Vehicles in this status show the customer of their latest BASTK.',
    )

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
