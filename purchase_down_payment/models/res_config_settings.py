# -*- coding: utf-8 -*-
################################################################################
#
#    Cybrosys Technologies Pvt. Ltd.
#
#    Copyright (C) 2024-TODAY Cybrosys Technologies(<https://www.cybrosys.com>).
#    Author: Ashwin T (odoo@cybrosys.com)
#
#    You can modify it under the terms of the GNU AFFERO
#    GENERAL PUBLIC LICENSE (AGPL v3), Version 3.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU AFFERO GENERAL PUBLIC LICENSE (AGPL v3) for more details.
#
#    You should have received a copy of the GNU AFFERO GENERAL PUBLIC LICENSE
#    (AGPL v3) along with this program.
##############################################################################
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    """The class is to created for inherited the model Res Config Settings"""
    _inherit = 'res.config.settings'

    po_deposit_default_product_id = fields.Many2one(
        'product.product',
        'PO Deposit Product',
        domain="[('type', '=', 'service')]",
        config_parameter='purchase_down_payment.po_deposit_default_product_id',
        help='Default product used for payment advances in purchase order')
    leasing_admin_product_id = fields.Many2one(
        'product.product',
        'Leasing Admin Fee Product',
        domain="[('type', '=', 'service')]",
        config_parameter='purchase_down_payment.leasing_admin_product_id',
        help='Product used for Biaya Admin Leasing in DP Invoice')
    leasing_ap_product_id = fields.Many2one(
        'product.product',
        'Leasing First Installment Product',
        domain="[('type', '=', 'service')]",
        config_parameter='purchase_down_payment.leasing_ap_product_id',
        help='Product used for AP Leasing-Angsuran Pertama in DP Invoice')
