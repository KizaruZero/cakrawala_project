# from odoo import models, fields, api


# class x_bastk_management(models.Model):
#     _name = 'x_bastk_management.x_bastk_management'
#     _description = 'x_bastk_management.x_bastk_management'

#     name = fields.Char()
#     value = fields.Integer()
#     value2 = fields.Float(compute="_value_pc", store=True)
#     description = fields.Text()
#
#     @api.depends('value')
#     def _value_pc(self):
#         for record in self:
#             record.value2 = float(record.value) / 100

