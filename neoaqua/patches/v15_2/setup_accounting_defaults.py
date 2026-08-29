# Copyright (c) 2026, Neotec Integrated Solutions
"""v15.2.0 - accounting defaults.

Sites installed on 15.0.0 or 15.1.x have items without income or expense
accounts, which blocks the first sales invoice. This backfills the chart of
accounts, cost centers, warehouse account mapping and item defaults.
"""

import frappe

from neoaqua.setup import accounts, custom_fields, masters


def execute():
	custom_fields.install()

	companies = frappe.get_all("Company", pluck="name")
	if len(companies) != 1:
		return
	company = companies[0]

	# nothing to backfill on a site that never ran the plant seeder
	if not frappe.db.exists("Item", "FG-BOT-600"):
		return

	try:
		accounts.run(company)
		masters.create_items(company)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "NeoAqua v15.2.0 accounting backfill")
