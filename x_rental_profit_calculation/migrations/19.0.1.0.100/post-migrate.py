# -*- coding: utf-8 -*-
import re

from odoo import SUPERUSER_ID, api


def _normalize(value):
    return re.sub(r'[^a-z0-9]+', '', (value or '').lower())


def _best_variant(variants, legacy_brand, legacy_type):
    """Return one unambiguous product variant matching the legacy text."""
    brand_key = _normalize(legacy_brand)
    type_key = _normalize(legacy_type)
    combined_key = _normalize(' '.join(filter(None, (
        legacy_brand, legacy_type,
    ))))
    scored = []
    for variant in variants:
        display_key = _normalize(variant.display_name)
        template_key = _normalize(variant.product_tmpl_id.name)
        score = 0
        if type_key and type_key == display_key:
            score = 100
        elif combined_key and combined_key == display_key:
            score = 95
        elif (
            brand_key and type_key
            and brand_key in display_key
            and type_key in display_key
        ):
            score = 90
        elif type_key and len(type_key) >= 4 and type_key in display_key:
            score = 70
        elif brand_key and brand_key == template_key:
            score = 50
        if score:
            scored.append((score, variant))

    if not scored:
        return variants.browse()
    best_score = max(score for score, variant in scored)
    best = [variant for score, variant in scored if score == best_score]
    return best[0] if len(best) == 1 else variants.browse()


def migrate(cr, version):
    """Map legacy RPC vehicle text to the shared CRM Product Variant master."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    documents = env['rpc.document'].with_context(active_test=False).search([])
    variants = env['product.product'].with_context(active_test=False).search([
        ('product_tmpl_id.is_vehicle', '=', True),
    ])
    templates = variants.product_tmpl_id

    for document in documents:
        template = document.merek_product_tmpl_id
        variant = document.type_kendaraan_id
        lead = document.crm_lead_id

        if lead:
            lead_brand_field = lead._fields.get('merek_id')
            lead_variant_field = lead._fields.get('tipe_kendaraan_id')
            if (
                lead_brand_field
                and lead_brand_field.comodel_name == 'product.template'
                and lead.merek_id
            ):
                template = lead.merek_id
            if (
                lead_variant_field
                and lead_variant_field.comodel_name == 'product.product'
                and lead.tipe_kendaraan_id
            ):
                variant = lead.tipe_kendaraan_id
                template = variant.product_tmpl_id

        legacy_brand = document.merek_id.name if document.merek_id else ''
        legacy_type = document.type_kendaraan or ''
        if not variant:
            variant = _best_variant(variants, legacy_brand, legacy_type)
            if variant:
                template = variant.product_tmpl_id

        if not template and legacy_brand:
            exact_templates = templates.filtered(
                lambda candidate: (
                    _normalize(candidate.name) == _normalize(legacy_brand)
                )
            )
            if len(exact_templates) == 1:
                template = exact_templates

        values = {}
        if template and document.merek_product_tmpl_id != template:
            values['merek_product_tmpl_id'] = template.id
        if variant and document.type_kendaraan_id != variant:
            values['type_kendaraan_id'] = variant.id
        if values:
            document.write(values)
