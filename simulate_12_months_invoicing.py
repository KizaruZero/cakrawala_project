# -*- coding: utf-8 -*-
"""
Simulate 12 Months Rental Invoicing Script
-------------------------------------------
Usage:
    python simulate_12_months_invoicing.py SO/CRS/07/2026/00075

This script connects to the Odoo database ('cakrawala_dev') and simulates advancing
time month-by-month to generate all 12 draft invoices for the given Rental Order
instantly, without altering your computer's local system clock.
"""

import sys
import os
import argparse
from datetime import date

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# Append Odoo core directory to sys.path
ODOO_PATH = r"D:\Odoo\odoo"
if ODOO_PATH not in sys.path:
    sys.path.append(ODOO_PATH)

import odoo
from odoo import api, SUPERUSER_ID
from odoo.modules.registry import Registry


def run_simulation(so_name, db_name="cakrawala_dev"):
    print("=" * 75)
    print(f"[START] 12-MONTH INVOICING SIMULATION FOR: {so_name}")
    print("=" * 75)

    # Initialize Odoo configuration and database connection
    odoo.tools.config.parse_config(['-c', r'D:\Odoo\odoo.conf', '-d', db_name])
    registry = Registry(db_name)

    with registry.cursor() as cr:
        env = api.Environment(cr, SUPERUSER_ID, {})
        
        so = env['sale.order'].search([('name', '=', so_name)], limit=1)
        if not so:
            print(f"[ERROR] Rental Order '{so_name}' not found in database '{db_name}'.")
            return

        if not so.is_rental_order:
            print(f"[ERROR] Order '{so_name}' is not marked as a Rental Order (is_rental_order=False).")
            return

        if so.state != 'sale':
            print(f"[WARNING] Order '{so_name}' is currently in state '{so.state}'. It must be Confirmed (state='sale') to generate invoices.")
            print("Trying to proceed anyway...")

        print(f"Contract Details:")
        print(f"   - Customer       : {so.partner_id.name}")
        print(f"   - Rental Period  : {so.rental_start_date} -> {so.rental_return_date}")
        print(f"   - Cycle Period   : {so.invoicing_cycle_period}")
        print(f"   - Consolidate    : {so.consolidate_invoice}")
        print(f"   - TOP & Rule     : {so.top_billing} / {so.billing_rule}")
        print("-" * 75)

        # Count existing rental invoices
        existing_invs = env['account.move'].search([('invoice_origin', '=', so.name), ('x_is_rental_invoice', '=', True)], order='id asc')
        print(f"Existing Rental Invoices before simulation ({len(existing_invs)} found):")
        for inv in existing_invs:
            print(f"   * ID: {inv.id} | Name: {inv.name or 'Draft'} | Date: {inv.invoice_date} | Total: {inv.amount_total:,.2f}")
        print("-" * 75)

        # Simulate clicking 'Simulate Next Cycle Invoice' or advancing time loop
        print("Simulating Month-by-Month Invoice Generation...\n")
        
        cycle_count = 0
        max_cycles = 40  # Safety limit to prevent infinite loops

        while cycle_count < max_cycles:
            before_ids = set(env['account.move'].search([('invoice_origin', '=', so.name), ('x_is_rental_invoice', '=', True)]).ids)
            
            # Call our UI simulation logic method
            so.action_simulate_next_cycle_invoice()
            
            after_invs = env['account.move'].search([('invoice_origin', '=', so.name), ('x_is_rental_invoice', '=', True)], order='id asc')
            after_ids = set(after_invs.ids)
            new_ids = after_ids - before_ids

            if not new_ids:
                print("[DONE] All due cycles have been generated! No more invoices created.")
                break

            cycle_count += 1
            for new_id in sorted(new_ids):
                new_inv = env['account.move'].browse(new_id)
                print(f"[Cycle {cycle_count}] Generated Draft Invoice ID: {new_inv.id} | Date: {new_inv.invoice_date} | Total: {new_inv.amount_total:,.2f}")
                for line in new_inv.invoice_line_ids:
                    if line.product_id:
                        desc_first_line = (line.name or '').split('\n')[0]
                        desc_period = (line.name or '').split('\n')[1] if '\n' in (line.name or '') else ''
                        print(f"     -> Line: {desc_first_line} | Period: {desc_period} | Qty: {line.quantity} | Amount: {line.price_subtotal:,.2f}")
            print()

        cr.commit()
        print("=" * 75)
        print(f"[COMPLETE] SIMULATION FINISHED! Total Invoices for '{so_name}': {len(after_invs)}")
        print("=" * 75)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Simulate 12 Months Rental Invoicing for Odoo.")
    parser.add_argument("so_name", help="Sales Order / Rental Order Number (e.g. SO/CRS/07/2026/00075)")
    parser.add_argument("--db", default="cakrawala_dev", help="Database name (default: cakrawala_dev)")
    args = parser.parse_args()

    run_simulation(args.so_name, args.db)
