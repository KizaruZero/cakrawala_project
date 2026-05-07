from odoo import api, SUPERUSER_ID
from . import controllers
from . import models
import logging
_logger = logging.getLogger(__name__)

def post_init_hook(env):
    _logger.warning("POST INIT HOOK JALAN")

    action = env.ref('fleet.fleet_vehicle_log_contract_action', raise_if_not_found=False)
    if action:
        action.name = "Documents"