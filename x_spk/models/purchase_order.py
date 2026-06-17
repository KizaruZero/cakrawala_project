# -*- coding: utf-8 -*-
from odoo import fields, models


class PurchaseOrder(models.Model):
    _inherit = "purchase.order"

    fleet_spk_id = fields.Many2one(
        "fleet.spk",
        string="SPK",
        ondelete="set null",
        readonly=True,
        copy=False,
        help="Surat Perintah Kerja that generated this purchase order (external SPK).",
    )


class PurchaseOrderLine(models.Model):
    _inherit = "purchase.order.line"

    fleet_spk_id = fields.Many2one(
        related="order_id.fleet_spk_id",
        string="SPK Ref",
        store=True,
        readonly=True,
        copy=False,
    )
