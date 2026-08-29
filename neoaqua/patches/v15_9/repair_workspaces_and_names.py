# Copyright (c) 2026, Neotec Integrated Solutions
"""v15.9.3 — repair two things that shipped broken.

1. Workspaces rendered a header and one shortcut because their `content` JSON
   never referenced the link cards attached to them.
2. Product names were renamed on `tabItem` before the cascade existed, so BOMs,
   work orders and price lists kept the name they cached at creation.
"""

import frappe


def execute():
	try:
		from neoaqua.setup import dashboards

		dashboards.create_workspaces()
	except Exception:
		frappe.log_error(frappe.get_traceback(), "NeoAqua v15.9.3 workspace repair")

	try:
		from neoaqua.setup.brand import resync_brand_names

		if frappe.db.exists("Item", "FG-BOT-600"):
			resync_brand_names()
	except Exception:
		frappe.log_error(frappe.get_traceback(), "NeoAqua v15.9.3 name resync")
