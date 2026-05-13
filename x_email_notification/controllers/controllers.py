# from odoo import http


# class XEmailNotification(http.Controller):
#     @http.route('/x_email_notification/x_email_notification', auth='public')
#     def index(self, **kw):
#         return "Hello, world"

#     @http.route('/x_email_notification/x_email_notification/objects', auth='public')
#     def list(self, **kw):
#         return http.request.render('x_email_notification.listing', {
#             'root': '/x_email_notification/x_email_notification',
#             'objects': http.request.env['x_email_notification.x_email_notification'].search([]),
#         })

#     @http.route('/x_email_notification/x_email_notification/objects/<model("x_email_notification.x_email_notification"):obj>', auth='public')
#     def object(self, obj, **kw):
#         return http.request.render('x_email_notification.object', {
#             'object': obj
#         })

