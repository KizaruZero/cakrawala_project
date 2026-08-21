# Part of Odoo. See LICENSE file for full copyright and licensing details.

import re

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class ResPartner(models.Model):
    _inherit = 'res.partner'

    purchase_contact_person = fields.Char(string='Contact Person')

    # NPWP format baru (berbasis NIK) adalah 16 digit angka tanpa pemisah
    # titik/strip, jadi nilainya disimpan apa adanya sebagai 16 digit.
    _NPWP_PATTERN = re.compile(r'^\d{16}$')

    # Hanya field bisnis yang di-trigger, TANPA supplier_rank. supplier_rank
    # dinaikkan otomatis oleh account/purchase saat PO atau bill dikonfirmasi
    # (_increase_rank melakukan write biasa), sehingga kalau ikut di-trigger
    # vendor lama yang datanya belum lengkap akan menggagalkan konfirmasi PO.
    # --- Dicomment sementara untuk bypass mandatory di Vendor ---
    # @api.constrains('name', 'purchase_contact_person', 'street', 'phone', 'vat')
    # def _check_vendor_mandatory_fields(self):
    #     """Data wajib Vendor Master.
    #
    #     Hanya berlaku untuk partner yang sudah ditandai sebagai vendor
    #     (supplier_rank > 0 — di-set otomatis oleh action Vendors lewat
    #     default_supplier_rank), supaya contact dan customer biasa tidak
    #     ikut terkunci.
    #     """
    #     for rec in self:
    #         if not rec.supplier_rank:
    #             continue
    #
    #         missing = []
    #         if not rec.name:
    #             missing.append(_("Vendor Name"))
    #         if not rec.purchase_contact_person:
    #             missing.append(_("Contact Person"))
    #         if not rec.street:
    #             missing.append(_("Address"))
    #         if not rec.phone:
    #             missing.append(_("Phone Number"))
    #         if not rec.vat:
    #             missing.append(_("NPWP"))
    #         if missing:
    #             raise ValidationError(_(
    #                 "The following fields are required for vendor %(vendor)s: %(fields)s.",
    #                 vendor=rec.display_name or _("(new)"),
    #                 fields=", ".join(missing),
    #             ))
    #
    #         if not self._NPWP_PATTERN.match(rec.vat.strip()):
    #             raise ValidationError(_(
    #                 "NPWP must contain exactly 16 digits (numbers only).\n"
    #                 "Vendor: %(vendor)s\nNPWP entered: %(vat)s",
    #                 vendor=rec.display_name,
    #                 vat=rec.vat,
    #             ))

