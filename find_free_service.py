import psycopg2
conn = psycopg2.connect(host='localhost', port='5432', user='odoo', password='odoo', dbname='cakrawala_dev')
cur = conn.cursor()
cur.execute("UPDATE ir_ui_view SET active = False WHERE id IN (2685, 2686);")
conn.commit()
print('Deactivated.')
