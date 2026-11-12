"""Move the typed operational Kota/Kab and Provinsi of each vehicle onto the RPC masters.

The old free-text columns come from ``x_stock_asset_receipt`` and are still in the
table here: the ORM drops removed columns only once every module has loaded.

A text matches a master record by name, ignoring case and spacing. Nothing is
created in the masters, which CRM, RPC and Rental Order share. A text that matches
nothing is left empty and kept in the vehicle's chatter so the team can pick it again.
"""

import logging
import re

from markupsafe import Markup

from odoo import SUPERUSER_ID, api
from odoo.tools import sql

_logger = logging.getLogger(__name__)

TABLE = "fleet_vehicle"

# Common spellings of provinces the RPC master stores under a short name.
PROVINCE_ALIASES = {
    "aceh": "nad",
    "nanggroe aceh darussalam": "nad",
    "jakarta": "dki jakarta",
    "dki": "dki jakarta",
    "yogyakarta": "di yogyakarta",
    "diy": "di yogyakarta",
    "daerah istimewa yogyakarta": "di yogyakarta",
    "kepulauan riau": "kepri",
    "maluku utara": "malut",
    "kepulauan bangka belitung": "bangka belitung",
    "sumatra utara": "sumatera utara",
    "sumatra barat": "sumatera barat",
    "sumatra selatan": "sumatera selatan",
    "ntb": "nusa tenggara barat",
    "ntt": "nusa tenggara timur",
}
CITY_PREFIX = re.compile(r"^(kabupaten|kab\.?|kota)\s+")


def _key(text):
    return " ".join((text or "").lower().split())


def _bare(text):
    return CITY_PREFIX.sub("", _key(text))


def _match_city(cities, text):
    """Exact name first; without a Kab./Kota prefix only when that leaves a single city."""
    exact = [city for city in cities if _key(city.name) == _key(text)]
    if len(exact) == 1:
        return exact[0]
    bare = [city for city in cities if _bare(city.name) == _bare(text)]
    return bare[0] if not exact and len(bare) == 1 else None


def migrate(cr, version):
    if not all(sql.column_exists(cr, TABLE, column) for column in (
            "operational_city", "operational_province",
            "operational_city_id", "operational_province_id")):
        return
    env = api.Environment(cr, SUPERUSER_ID, {"active_test": False})
    provinces = {_key(province.name): province for province in env["rpc.provinsi"].search([])}
    cities = env["rpc.kota"].search([])

    cr.execute(f"""
        SELECT id, operational_city, operational_province FROM {TABLE}
         WHERE COALESCE(TRIM(operational_city), '') != ''
            OR COALESCE(TRIM(operational_province), '') != ''
    """)
    unmatched = {}
    rows = cr.fetchall()
    for vehicle_id, city_text, province_text in rows:
        province_key = _key(province_text)
        province = provinces.get(PROVINCE_ALIASES.get(province_key, province_key))
        city = None
        if _key(city_text):
            city = _match_city(cities.filtered(lambda c: c.provinsi_id == province) if province else cities,
                               city_text)
            province = province or (city and city.provinsi_id)
        cr.execute(f"UPDATE {TABLE} SET operational_city_id = %s, operational_province_id = %s WHERE id = %s",
                   (city.id if city else None, province.id if province else None, vehicle_id))
        lost = []
        if _key(city_text) and not city:
            lost.append(("Kota/Kab", city_text.strip()))
        if _key(province_text) and not province:
            lost.append(("Provinsi", province_text.strip()))
        if lost:
            unmatched[vehicle_id] = lost

    for vehicle in env["fleet.vehicle"].browse(list(unmatched)):
        vehicle.message_post(body=Markup("%s<ul>%s</ul>%s") % (
            "Lokasi operasional sekarang dipilih dari master RPC. Isian lama berikut tidak ada di master:",
            Markup().join(Markup("<li>%s: %s</li>") % item for item in unmatched[vehicle.id]),
            "Silakan pilih ulang setelah datanya ditambahkan di RPC → Konfigurasi.",
        ))
    _logger.info("Operational location: %s vehicles moved to the RPC masters, %s with text not found.",
                 len(rows), len(unmatched))
