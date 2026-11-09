import logging

from odoo import SUPERUSER_ID, api


_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Preserve each existing OTR mapping, including archived/custom categories.

    Never overwrite an already populated relation or recompute historical RPCs:
    their selected category can be an intentional manual override.
    """
    env = api.Environment(cr, SUPERUSER_ID, {'active_test': False})
    categories = env['rpc.kendaraan.kategori'].search([
        ('jenis_kendaraan_ids', '=', False),
    ])
    for category in categories:
        if category.jenis_kendaraan_id:
            category.write({'jenis_kendaraan_id': category.jenis_kendaraan_id.id})
        elif category.jenis_kendaraan:
            category.write({'jenis_kendaraan': category.jenis_kendaraan})
        else:
            _logger.warning('OTR category %s has no legacy vehicle type to migrate.', category.id)
    _logger.info('Migrated vehicle-type mappings for %s OTR categories.', len(categories))
