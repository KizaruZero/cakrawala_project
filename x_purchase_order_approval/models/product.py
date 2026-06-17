# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
# from odoo.addons.base.models.res_partner import WARNING_MESSAGE, WARNING_HELP
from odoo.tools.float_utils import float_round
from odoo.exceptions import UserError
from dateutil.relativedelta import relativedelta


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    product_maker = fields.Char('Maker', copy=False)
    product_type = fields.Char('Type', copy=False)
    product_dwg_number = fields.Char('DWG Number', copy=False)
    product_fin_plan = fields.Char('Fin. Plan', copy=False)
    product_serial_number = fields.Char('Serial Number', copy=False)
    product_part_no = fields.Char('Part No.', copy=False)