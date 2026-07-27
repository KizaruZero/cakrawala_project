# Customer Statement of Account

Create a PDF Statement of Account and an email draft from selected customer invoices.

## Installation

1. Extract this module into your Odoo custom addons directory.
2. Update the Apps list.
3. Install **Customer Statement of Account**.

## Usage

1. Go to **Accounting > Customers > Invoices**.
2. Select one or more posted customer invoices for the same customer.
3. Click **Create SoA**.
4. Download the PDF from the attachment chip if required, then send the email.

The customer must be the same across all selected invoices. The email composer uses the customer's email address when available.

The PDF address is read from the selected customer's master data: street, additional
street, city, state, postal code, and country.

## PDF prerequisite

Odoo needs `wkhtmltopdf` installed on the Odoo server to create PDF reports. Install a
version supported by your Odoo 19 deployment, restart the Odoo service, and confirm that
the `wkhtmltopdf` executable is available to that service's PATH.
