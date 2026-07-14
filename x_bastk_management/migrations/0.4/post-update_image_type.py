from odoo import api, SUPERUSER_ID

def migrate(cr, version):
    if not version:
        return
    
    env = api.Environment(cr, SUPERUSER_ID, {})
    
    # Update any existing bastk management image to 'keluar'
    cr.execute("UPDATE bastk_management_image SET bastk_type = 'keluar' WHERE bastk_type IS NULL")
