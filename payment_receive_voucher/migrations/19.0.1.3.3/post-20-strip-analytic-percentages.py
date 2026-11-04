import ast
import re

from odoo import SUPERUSER_ID, api, _


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    Detail = env['prv.voucher.detail'].sudo()
    Account = env['account.analytic.account'].sudo()
    last_id = 0
    while True:
        records = Detail.search([('id', '>', last_id), ('analytic', '!=', False)], order='id', limit=500)
        if not records:
            break
        all_ids = set()
        parsed = {}
        for rec in records:
            try:
                value = ast.literal_eval(rec.analytic)
            except (ValueError, SyntaxError, TypeError):
                value = None
            if isinstance(value, dict):
                parsed[rec.id] = value
                for key in value:
                    all_ids.update(int(part) for part in str(key).split(',') if part.strip().isdigit())
            else:
                parsed[rec.id] = rec.analytic
        names = {account.id: account.display_name for account in Account.browse(list(all_ids)).exists()}
        for rec in records:
            value = parsed[rec.id]
            if isinstance(value, dict):
                items = []
                for key in value:
                    items.extend(names.get(int(part), _('Unknown analytic account'))
                                 for part in str(key).split(',') if part.strip().isdigit())
            else:
                items = []
                for part in re.split(r'\s*;\s*', value or ''):
                    part = re.sub(r'\s*\([0-9]+(?:\.[0-9]+)?%\)\s*$', '', part).strip()
                    items.extend(label.strip() for label in part.split(' / ') if label.strip())
            rec._internal_write({'analytic': ', '.join(dict.fromkeys(items))})
        last_id = records[-1].id
