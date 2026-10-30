from ast import literal_eval

from odoo import SUPERUSER_ID, api, _


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    Detail = env['prv.voucher.detail'].sudo()
    Account = env['account.analytic.account'].sudo()
    last_id = 0
    while True:
        details = Detail.search([('id', '>', last_id), ('analytic', '!=', False)], order='id', limit=500)
        if not details:
            break
        distributions, all_ids = {}, set()
        for detail in details:
            try:
                value = literal_eval(detail.analytic)
            except (ValueError, SyntaxError, TypeError):
                value = None
            if not isinstance(value, dict):
                distributions[detail.id] = None
                continue
            distributions[detail.id] = value
            for key in value:
                all_ids.update(int(part) for part in str(key).split(',') if part.strip().isdigit())
        names = {account.id: account.display_name for account in Account.browse(list(all_ids)).exists()}
        for detail in details:
            distribution = distributions.get(detail.id)
            if distribution is None:
                continue
            parts = []
            for key, percentage in distribution.items():
                labels = [names.get(int(part), _('Unknown analytic account'))
                          for part in str(key).split(',') if part.strip().isdigit()]
                if labels:
                    parts.append('%s (%.2f%%)' % (' / '.join(labels), float(percentage)))
            detail._internal_write({'analytic': '; '.join(parts)})
        last_id = details[-1].id
