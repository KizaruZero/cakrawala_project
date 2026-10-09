"""Ensure section headers exist for existing BASTK records after upgrading to 0.9."""

from odoo import api, SUPERUSER_ID
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    if 'bastk.description' in env:
        try:
            env['bastk.description']._ensure_bastk_section_headers()
            _logger.info("BASTK migration 0.9: Section headers ensured.")
        except Exception as e:
            _logger.warning("BASTK migration 0.9: Failed to ensure section headers: %s", e)
