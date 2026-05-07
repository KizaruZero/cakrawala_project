from odoo import models

class IrSequence(models.Model):
    _inherit = 'ir.sequence'

    def _get_prefix_suffix(self, date=None, date_range=None):
        def _interpolate(s, d):
            return (s % d) if s else ''

        def _interpolation_dict():
            from datetime import datetime
            now = range_date = effective_date = datetime.now(self.env.tz)
            if date or self.env.context.get('ir_sequence_date'):
                from odoo import fields
                effective_date = fields.Datetime.from_string(date or self.env.context.get('ir_sequence_date'))
            if date_range or self.env.context.get('ir_sequence_date_range'):
                from odoo import fields
                range_date = fields.Datetime.from_string(date_range or self.env.context.get('ir_sequence_date_range'))

            sequences = {
                'year': '%Y', 'month': '%m', 'day': '%d', 'y': '%y', 'doy': '%j', 'woy': '%W',
                'weekday': '%w', 'h24': '%H', 'h12': '%I', 'min': '%M', 'sec': '%S',
                'isoyear': '%G', 'isoy': '%g', 'isoweek': '%V',
            }
            res = {}
            for key, format in sequences.items():
                res[key] = effective_date.strftime(format)
                res['range_' + key] = range_date.strftime(format)
                res['current_' + key] = now.strftime(format)
            
            company = self.company_id or self.env.company
            company_code = getattr(company, 'company_code', '') or getattr(company, 'code', '') or ''
            res['company_code'] = company_code
            return res

        self.ensure_one()
        d = _interpolation_dict()
        try:
            interpolated_prefix = _interpolate(self.prefix, d)
            interpolated_suffix = _interpolate(self.suffix, d)
        except (ValueError, TypeError, KeyError):
            from odoo.exceptions import UserError
            from odoo import _
            raise UserError(_('Invalid prefix or suffix for sequence “%s”', self.name))
        return interpolated_prefix, interpolated_suffix
