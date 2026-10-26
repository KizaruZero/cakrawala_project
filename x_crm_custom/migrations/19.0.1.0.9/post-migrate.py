import logging

from odoo import api, SUPERUSER_ID


_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Move the old PIC link to its own field; never rewrite linked RPC/SO."""
    env = api.Environment(cr, SUPERUSER_ID, {
        'active_test': False, 'tracking_disable': True, 'mail_create_nosubscribe': True,
    })
    leads = env['crm.lead'].search([
        ('partner_id.is_company', '=', False),
        ('partner_id.commercial_partner_id.is_company', '=', True),
    ])
    count = 0
    for lead in leads:
        contact = lead.partner_id
        company = contact.commercial_partner_id
        if lead.contact_partner_id and lead.contact_partner_id != contact:
            _logger.warning('CRM lead %s has a conflicting PIC; left unchanged for review.', lead.id)
            continue
        if contact.type != 'contact':
            continue
        # Preserve manually entered lead snapshots, filling only empty values.
        lead.write({
            'partner_id': company.id, 'contact_partner_id': contact.id,
            'contact_name': lead.contact_name or contact.name,
            'job_position': lead.job_position or lead.function or contact.function,
            'function': lead.function or lead.job_position or contact.function,
            'email_from': lead.email_from or contact.email,
            'phone': lead.phone or contact.phone,
        })
        count += 1
    _logger.info('Separated company/PIC on %s legacy CRM leads; linked RPC/SO unchanged.', count)
