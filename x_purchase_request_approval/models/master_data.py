# -*- coding: utf-8 -*-

from datetime import datetime
from odoo import api, fields, models, tools, _
from odoo.exceptions import ValidationError


class PurchaseRequestTypeMaster(models.Model):
    _name = "purchase.request.type.master"
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = "Purchase Request type"

    name = fields.Char(string='Name', required=True, copy=False)
    state = fields.Selection([('draft', 'Draft'), ('active', 'Active')], default='draft', string='Status')
    company_id = fields.Many2one('res.company', 'Company', required=True, default=lambda self: self.env.company.id, index=True)
    active = fields.Boolean("Active", default=True)

    _sql_constraints = [('unique_code', 'UNIQUE(name,company_id)', "Name must be unique")]


    def button_draft(self):
        for record in self:
            if record.state not in ['active']:
                continue
            record.write({'state': 'draft'})
        return True

    def button_confirm(self):
        for record in self:
            if record.state not in ['draft']:
                continue
            record.write({'state': 'active'})
        return True


class PurchaseRequestApprovalConfigMaster(models.Model):
    _name = "purchase.request.approval.config.master"
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = "Purchase Request Approval Config"

    name = fields.Char(string='Name', required=True, copy=False, default='/')
    currency_id = fields.Many2one('res.currency', 'Currency', required=True, default=lambda self: self.env.company.currency_id.id)
    purchase_request_type_id = fields.Many2one('purchase.request.type.master', string='PR Type', required=True, tracking=True, check_company=True,
        domain="[('state', '=', 'active'), ('active','=',True)]")
    department_id = fields.Many2one("hr.department", string='Division', required=True)
    sequence = fields.Integer(default=1)
    starting_amount = fields.Monetary(string='Starting Amount', tracking=True)
    approver_id = fields.Many2one('res.users', string="Approver", required=True, domain="[('share', '=', False), ('active','=',True)]")
    delegation_id = fields.Many2one('res.users', string="Delegation", required=False, domain="[('share', '=', False), ('active','=',True)]")
    date_valid_from = fields.Date('Valid From', copy=False, default=fields.Date.context_today)
    date_valid_to = fields.Date('Valid To', copy=False, default=fields.Date.context_today)
    state = fields.Selection([('draft', 'Draft'), ('active', 'Active')], default='draft', string='Status')
    company_id = fields.Many2one('res.company', 'Company', required=True, default=lambda self: self.env.company.id, index=True)
    active = fields.Boolean("Active", default=True)


    def button_draft(self):
        for record in self:
            if record.state not in ['active']:
                continue
            record.write({'state': 'draft'})
        return True

    def button_confirm(self):
        for record in self:
            if record.state not in ['draft']:
                continue
            name = f"{record.company_id.company_code}/{record.purchase_request_type_id.name}/{record.department_id.name}/{record.sequence}"

            dup = self.search_count([
                ('id', '!=', record.id),
                ('name', '=', name),
                ('company_id', '=', record.company_id.id),
                ('state', '=', 'active'),
                ('active', '=', True),
            ])
            if dup:
                raise ValidationError(
                    _("PR Approval with the same name already exist '%s', please create another one or modify existing data!!") % name
                )

            record.write({'name': name, 'state': 'active'})
        return True