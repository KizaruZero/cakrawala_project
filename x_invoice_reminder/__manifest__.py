{
    'name': 'x_invoice_reminder',

    'summary': 'Customer invoice due-date email reminders',
    'category': 'Accounting/Accounting',
    'description': """
Reminder email before a customer invoice reaches its due date.

Reuses the Notification Template engine (x_email_notification): the schedule is
configured as “End-date reminders” lines on the template with
«Use for = Invoice — customer invoice due-date reminders», exactly like the
BASTK and Fleet document reminders.
    """,

    'author': 'Custom',
    'version': '19.0.1.0.0',
    'license': 'LGPL-3',
    'application': False,
    'installable': True,

    'depends': ['account', 'mail', 'x_email_notification'],

    'data': [
        'data/invoice_due_mail_template.xml',
        'data/invoice_due_notification_data.xml',
        'data/invoice_due_notification_cron.xml',
        'views/notification_menu.xml',
    ],
}
