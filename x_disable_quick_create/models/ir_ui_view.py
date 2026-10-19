from odoo import models

ALLOWED_MODELS_PARAM = 'x_disable_quick_create.allowed_models'
BYPASS_GROUP = 'x_disable_quick_create.group_allow_quick_create'


class IrUiView(models.Model):
    _inherit = 'ir.ui.view'

    def _postprocess_access_rights(self, tree):
        # super() pops `model_access_rights` (the comodel of each editable
        # many2one/many2many field) and turns it into `can_create`, which every
        # relational widget reads to show "Create" / "Create and edit...".
        field_comodels = {
            node: node.get('model_access_rights')
            for node in tree.xpath('//field[@model_access_rights]')
        }
        tree = super()._postprocess_access_rights(tree)

        if (
            not field_comodels
            or self.env.context.get('studio')
            or self.env.user.has_group(BYPASS_GROUP)
        ):
            return tree

        allowed_models = self._get_quick_create_allowed_models()
        for node, comodel in field_comodels.items():
            if comodel not in allowed_models:
                node.set('can_create', 'False')
        return tree

    def _get_quick_create_allowed_models(self):
        value = self.env['ir.config_parameter'].sudo().get_param(ALLOWED_MODELS_PARAM) or ''
        return {name.strip() for name in value.split(',') if name.strip()}
