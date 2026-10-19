import logging

from odoo import SUPERUSER_ID, api


_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Refresh stored net resale prices, notes and losses, including archives.

    Always derive the price from OTR and the resale rate, not the previously
    stored price, so repeating the upgrade cannot deduct VAT a second time.
    Approval states, source inputs and financial schedules remain unchanged.
    """
    env = api.Environment(cr, SUPERUSER_ID, {
        'active_test': False,
        'tracking_disable': True,
        'mail_create_nosubscribe': True,
    })
    last_id = count = 0
    while documents := env['rpc.document'].search(
        [('id', '>', last_id)], order='id', limit=500,
    ):
        documents._compute_resale()
        documents._compute_catatan_rv()
        documents._compute_estimasi_loss_nilai_buku()
        documents.flush_recordset([
            'resale_price', 'total_accum_saat_dispose', 'nilai_buku',
            'catatan_rv', 'estimasi_loss_nilai_buku',
        ])
        last_id = documents[-1].id
        count += len(documents)
    _logger.info('Updated VAT-exclusive resale prices for %s RPCs.', count)
