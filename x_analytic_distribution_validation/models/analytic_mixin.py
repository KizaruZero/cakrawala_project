# -*- coding: utf-8 -*-

import re

from odoo import _, api, models
from odoo.exceptions import ValidationError
from odoo.tools.float_utils import float_compare, float_round


class AnalyticMixin(models.AbstractModel):
    """Wajibkan analytic distribution bertotal tepat 100%.

    Odoo bawaan (``analytic.mixin._validate_distribution``) hanya memeriksa
    plan dengan applicability ``mandatory``, dan hanya ketika context
    ``validate_analytic`` diset. Kalau tidak ada plan mandatory, method itu
    langsung ``return`` sehingga distribusi 50% maupun 180% tetap lolos.

    Di sini pemeriksaan dijadikan constraint ORM biasa, sehingga berlaku pada
    setiap create/write dari mana pun asalnya (form, import, XML-RPC, kode
    modul lain).
    """
    _inherit = 'analytic.mixin'

    # Model yang distribusinya memang boleh parsial: template/model default dan
    # wizard transient. Menahan model-model ini pada 100% akan mematahkan
    # fungsionalitas standar Odoo.
    ANALYTIC_TOTAL_CHECK_EXCLUDED_MODELS = (
        'account.analytic.distribution.model',
        'account.reconcile.model',
        'hr.expense.split',
    )

    def _skip_analytic_distribution_total_check(self):
        """Hook: override untuk mengecualikan model/record tertentu."""
        self.ensure_one()
        return self._name in self.ANALYTIC_TOTAL_CHECK_EXCLUDED_MODELS

    def _analytic_distribution_total(self):
        """Total seluruh persentase pada analytic distribution satu record.

        Satu key JSON mewakili satu baris pada widget analytic distribution.
        Key bisa berupa gabungan beberapa account lintas plan (mis. ``"3,7"``),
        namun persentasenya tetap dihitung sekali, jadi penjumlahan datar di
        sini sudah setara dengan "total seluruh baris analytic".
        """
        self.ensure_one()
        return sum(
            percentage
            for key, percentage in (self.analytic_distribution or {}).items()
            # '__update__' hanya penanda multi-edit, isinya list nama field
            if key != '__update__' and isinstance(percentage, (int, float))
        )

    @api.constrains('analytic_distribution')
    def _check_analytic_distribution_total(self):
        # Escape hatch untuk skrip migrasi/perbaikan data massal.
        if self.env.context.get('skip_analytic_distribution_check'):
            return
        precision = self.env['decimal.precision'].precision_get('Percentage Analytic')
        for record in self:
            if record._skip_analytic_distribution_total_check():
                continue
            # Analytic distribution tetap boleh dikosongkan.
            if not record.analytic_distribution:
                continue
            total = record._analytic_distribution_total()
            if float_compare(total, 100.0, precision_digits=precision) == 0:
                continue
            total = float_round(total, precision_digits=precision)
            gap = float_round(abs(100.0 - total), precision_digits=precision)
            hint = _("kurang %s%%", gap) if total < 100.0 else _("kelebihan %s%%", gap)
            raise ValidationError(_(
                "Analytic distribution harus berjumlah tepat 100%%.\n\n"
                "%(document)s: total saat ini %(total)s%% (%(hint)s).\n\n"
                "Analytic distribution boleh dipecah menjadi beberapa baris, "
                "tetapi jumlah seluruh persentasenya wajib 100%%. "
                "Kosongkan analytic distribution apabila memang tidak dipakai.",
                document=record._analytic_distribution_error_label(),
                total=total,
                hint=hint,
            ))

    # Field many2one yang menunjuk ke dokumen induk, diperiksa berurutan.
    ANALYTIC_PARENT_FIELD_CANDIDATES = (
        'move_id',                  # account.move.line
        'order_id',                 # purchase.order.line / sale.order.line
        'requisition_product_id',   # requisition.order (PR line)
        'requisition_id',           # purchase.requisition.line
        'sheet_id',                 # hr.expense
    )

    # Field teks yang bisa dipakai sebagai deskripsi baris kalau tidak ada produk.
    ANALYTIC_DESCRIPTOR_FIELD_CANDIDATES = ('name', 'description', 'label', 'remark')

    def _analytic_distribution_error_label(self):
        """Label baris untuk pesan error.

        ``display_name`` tidak dipakai langsung karena model tanpa ``_rec_name``
        (mis. ``requisition.order``) menghasilkan ``requisition.order,33`` yang
        tidak berarti apa-apa bagi user. Sebagai gantinya label disusun dari
        dokumen induk + nomor baris + produk/deskripsi.
        """
        self.ensure_one()
        parts = []

        for fname in self.ANALYTIC_PARENT_FIELD_CANDIDATES:
            field = self._fields.get(fname)
            if field and field.type == 'many2one' and self[fname]:
                parts.append(self[fname].display_name)
                break

        if self._fields.get('line_no') and self.line_no:
            parts.append(_("baris %s", self.line_no))

        descriptor = self._analytic_distribution_descriptor()
        if descriptor:
            parts.append(descriptor)

        if not parts:
            parts.append(self.env['ir.model']._get(self._name).name or self._name)
        return ' / '.join(parts)

    def _analytic_distribution_descriptor(self):
        """Deskripsi singkat baris: produk, lalu teks, lalu display_name."""
        self.ensure_one()
        descriptor = False
        if self._fields.get('product_id') and self.product_id:
            descriptor = self.product_id.display_name
        if not descriptor:
            for fname in self.ANALYTIC_DESCRIPTOR_FIELD_CANDIDATES:
                field = self._fields.get(fname)
                if field and field.type in ('char', 'text') and self[fname]:
                    descriptor = self[fname]
                    break
        if not descriptor:
            name = self.display_name or ''
            # Buang fallback bawaan Odoo berbentuk "model.name,42".
            descriptor = False if re.match(r'^[\w.]+,\d+$', name) else name
        if not descriptor:
            return False
        descriptor = descriptor.splitlines()[0].strip()
        return descriptor if len(descriptor) <= 80 else descriptor[:77] + '...'
