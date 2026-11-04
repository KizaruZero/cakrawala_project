from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError

PARAM_DB = 'x_data_cleanup.unlocked_db'
PARAM_UUID = 'x_data_cleanup.unlocked_uuid'
PARAM_UNTIL = 'x_data_cleanup.unlocked_until'
UNLOCK_HOURS = 4


class CleanupGuard(models.AbstractModel):
    """ A cleanup only runs on a database unlocked on purpose, for a few hours. The unlock is tied to the
    name and the UUID of the database: a copy restored elsewhere, or the same database hours later, is
    locked again. """
    _name = 'x.cleanup.guard'
    _description = 'Data Cleanup: Pengaman'

    @api.model
    def _params(self):
        return self.env['ir.config_parameter'].sudo()

    @api.model
    def check_admin(self):
        if not self.env.user.has_group('base.group_system'):
            raise AccessError(_('Hanya Administrator (Settings) yang boleh membersihkan data.'))

    @api.model
    def unlocked_until(self):
        params = self._params()
        if params.get_param(PARAM_DB) != self.env.cr.dbname or \
                params.get_param(PARAM_UUID) != params.get_param('database.uuid'):
            return False
        until = params.get_param(PARAM_UNTIL)
        until = fields.Datetime.to_datetime(until) if until else False
        return until if until and until > fields.Datetime.now() else False

    @api.model
    def check_unlocked(self):
        self.check_admin()
        if not self.unlocked_until():
            raise UserError(_(
                'Database ini terkunci untuk pembersihan data. Buka kunci dulu di Data Cleanup > Dashboard '
                '(berlaku %s jam, hanya untuk database ini).', UNLOCK_HOURS))

    @api.model
    def unlock(self):
        self.check_admin()
        params = self._params()
        params.set_param(PARAM_DB, self.env.cr.dbname)
        params.set_param(PARAM_UUID, params.get_param('database.uuid'))
        params.set_param(PARAM_UNTIL, fields.Datetime.to_string(fields.Datetime.now() + timedelta(hours=UNLOCK_HOURS)))

    @api.model
    def lock(self):
        self.check_admin()
        params = self._params()
        for key in (PARAM_DB, PARAM_UUID, PARAM_UNTIL):
            params.set_param(key, False)
