from odoo import models, fields, api, _

class SaleOrder(models.Model):
    _inherit = 'sale.order'

    bastk_id = fields.Many2one('bastk.management', string='BASTK', readonly=True)
    bastk_reference = fields.Char(string='BASTK Reference', related='bastk_id.name', readonly=True)
    bastk_date = fields.Date(string='BASTK Date', related='bastk_id.start_date', readonly=True)

    def action_create_bastk(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('x_bastk_management.action_bastk')
        
        action['context'] = {
            'default_sale_order_id': self.id,
            'default_partner_id': self.partner_id.id,
        }
        action['views'] = [(self.env.ref('x_bastk_management.view_bastk_form').id, 'form')]
        return action
