# from odoo import http


# class XBastkManagement(http.Controller):
#     @http.route('/x_bastk_management/x_bastk_management', auth='public')
#     def index(self, **kw):
#         return "Hello, world"

#     @http.route('/x_bastk_management/x_bastk_management/objects', auth='public')
#     def list(self, **kw):
#         return http.request.render('x_bastk_management.listing', {
#             'root': '/x_bastk_management/x_bastk_management',
#             'objects': http.request.env['x_bastk_management.x_bastk_management'].search([]),
#         })

#     @http.route('/x_bastk_management/x_bastk_management/objects/<model("x_bastk_management.x_bastk_management"):obj>', auth='public')
#     def object(self, obj, **kw):
#         return http.request.render('x_bastk_management.object', {
#             'object': obj
#         })

