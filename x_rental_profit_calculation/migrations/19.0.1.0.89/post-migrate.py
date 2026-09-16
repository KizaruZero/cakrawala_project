from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    """Link an unambiguous legacy rental quotation to its RPC document."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    sale_order_model = env['sale.order']
    sale_fields = sale_order_model._fields

    # The former create action did not store an RPC reference.  Opportunity
    # and rental fields are the strongest identifiers available for those
    # legacy quotations.  Ambiguous matches are deliberately left unlinked.
    if not {'opportunity_id', 'is_rental_order'}.issubset(sale_fields):
        return

    documents = env['rpc.document'].with_context(active_test=False).search([
        ('quotation_ids', '=', False),
        ('crm_lead_id', '!=', False),
    ])
    for document in documents:
        domain = [
            ('rpc_document_id', '=', False),
            ('opportunity_id', '=', document.crm_lead_id.id),
            ('partner_id', '=', document.partner_id.id),
            ('is_rental_order', '=', True),
        ]
        if 'masa_sewa_bulan' in sale_fields:
            domain.append(('masa_sewa_bulan', '=', document.masa_sewa))
        if 'order_type_id' in sale_fields and document.jenis_transaksi_id:
            domain.append((
                'order_type_id', '=', document.jenis_transaksi_id.id,
            ))
        if 'location_id' in sale_fields and document.kota_id:
            domain.append(('location_id', '=', document.kota_id.id))
        if (
            'rental_type_id' in sale_fields
            and 'rental_type_id' in document.crm_lead_id._fields
            and document.crm_lead_id.rental_type_id
        ):
            domain.append((
                'rental_type_id', '=',
                document.crm_lead_id.rental_type_id.id,
            ))

        candidates = sale_order_model.search(domain, limit=2)
        if len(candidates) == 1:
            candidates.rpc_document_id = document.id
