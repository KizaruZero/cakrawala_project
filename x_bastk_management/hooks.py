import logging

_logger = logging.getLogger(__name__)


def post_init_hook(env):
    """Pastikan section header dibuat untuk BASTK yang sudah ada setelah data XML ter-load."""
    try:
        env['bastk.description']._ensure_bastk_section_headers()
        _logger.info("BASTK post_init_hook: Section headers successfully ensured.")
    except Exception as e:
        _logger.warning("BASTK post_init_hook encountered an issue: %s", e)
