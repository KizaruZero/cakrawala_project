{
    "name": "x_helpdesk_enhance",
    "version": "19.0.1.0.0",
    "category": "Services/Helpdesk",
    "summary": "Enhancement Helpdesk: ticket number, category, dan trigger BAK/SPK",
    "description": """
Enhance Helpdesk:
- Auto ticket number berdasarkan kode team
- Master code untuk Helpdesk Team
- Master ticket category
- Trigger create BAK/SPK dari ticket
    """,
    "author": "Cakrawala",
    "license": "LGPL-3",
    "depends": [
        "helpdesk",
        "x_bak",
        "x_spk"
    ],
    "data": [
        "security/ir.model.access.csv",
        "data/helpdesk_ticket_category_data.xml",
        "data/helpdesk_ticketing_category_data.xml",
        "data/helpdesk_team_data.xml",
        "views/helpdesk_team_views.xml",
        "views/helpdesk_ticket_category_views.xml",
        "views/helpdesk_ticketing_category_views.xml",
        "views/helpdesk_ticket_views.xml",
        "views/bak_views.xml",
        "views/fleet_spk_views.xml"
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
}
