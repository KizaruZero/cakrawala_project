# -*- coding: utf-8 -*-
from odoo import models


class AccountMove(models.Model):
    """Payment Date is derived by account.loan.line from posted payment moves."""
    _inherit = 'account.move'
