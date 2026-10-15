import logging

from odoo import SUPERUSER_ID, api
from odoo.exceptions import ValidationError


_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Fill annual Operation costs without rewriting completed Finance RPCs."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    documents = env['rpc.document'].search([
        ('state', 'in', ['draft', 'submitted', 'procurement_done', 'operation_done']),
        ('tahun_mulai_sewa', '>', 0),
        ('masa_sewa', '>', 0),
    ])
    for document in documents:
        try:
            with cr.savepoint():
                document._sync_operational_line_years()
        except ValidationError as error:
            # A populated cost outside the requested duration needs a human
            # decision. Preserve the entire document instead of losing rates.
            _logger.warning(
                'RPC annual Operation costs left unchanged for %s: %s',
                document.name, error,
            )
