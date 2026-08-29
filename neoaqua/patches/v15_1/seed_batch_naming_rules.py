# Copyright (c) 2026, Neotec Integrated Solutions
"""v15.1.0 - seed the default batch naming rules."""

import frappe

from neoaqua.setup import batch_rules, custom_fields


def execute():
	custom_fields.install()
	companies = frappe.get_all("Company", pluck="name")
	if len(companies) != 1:
		return
	try:
		batch_rules.run(companies[0])
	except Exception:
		frappe.log_error(frappe.get_traceback(), "NeoAqua v15.1.0 batch rule seeding")
