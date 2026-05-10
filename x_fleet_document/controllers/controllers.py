# from odoo import http


# class XFleetGr(http.Controller):
#     @http.route('/x_fleet_gr/x_fleet_gr', auth='public')
#     def index(self, **kw):
#         return "Hello, world"

#     @http.route('/x_fleet_gr/x_fleet_gr/objects', auth='public')
#     def list(self, **kw):
#         return http.request.render('x_fleet_gr.listing', {
#             'root': '/x_fleet_gr/x_fleet_gr',
#             'objects': http.request.env['x_fleet_gr.x_fleet_gr'].search([]),
#         })

#     @http.route('/x_fleet_gr/x_fleet_gr/objects/<model("x_fleet_gr.x_fleet_gr"):obj>', auth='public')
#     def object(self, obj, **kw):
#         return http.request.render('x_fleet_gr.object', {
#             'object': obj
#         })

