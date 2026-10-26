# CRM company and contact (19.0.1.0.9)

Deploy and upgrade `x_crm_custom`; no staging records are changed by the source
patch itself.

Quick Create now selects **Company** (`partner_id`) first, then **Contact**
(`contact_partner_id`) from that company's contact persons. The full form uses
the same separation for Existing Customer and Contact Name. Contact selection
copies the PIC's name, job position (`res.partner.function`), email and phone
onto the lead. The address and customer for newly created RPCs remain the
company. Opportunity-name uppercasing and stage requirements are retained.

The copied details remain editable snapshots. Unrelated saves or master-data
changes do not reset manually entered lead details. Changing company clears a
PIC from a different company, and selecting an unrelated PIC is rejected on
the server as well as filtered in the form. Lead email/phone edits while a PIC
is selected do not write PIC data onto the company's or contact's master data.

API/import calls that still send a company-owned contact as `partner_id` are
normalized to company + PIC. Standalone historical individuals are not assigned
an invented company. The New Customer/Offering flow creates a company and a
separate child contact when a contact name was supplied.

On upgrade, the versioned migration separates old leads whose customer is
still a contact person under a company, including archived leads/contacts. It
preserves manual details, fills missing job information, and does not rename
leads or change their stages. Conflicting explicit PIC links are left for
review, and no contact is guessed from a name. Existing RPCs, quotations,
orders and posted invoices are not re-linked or rewritten.
