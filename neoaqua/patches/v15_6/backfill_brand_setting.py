# Copyright (c) 2026, Neotec Integrated Solutions
"""v15.6.0 - move the brand out of the source and into Settings.

Sites seeded before the brand was configurable have item names carrying a
hardcoded brand. Detect it from an existing item and record it, so the rename
tool and any later re-seed have something to work from.
"""

import frappe


def execute():
	if frappe.db.get_single_value("NeoAqua Settings", "brand_name"):
		return

	brand = None
	name = frappe.db.get_value("Item", "FG-BOT-600", "item_name")
	if name:
		for suffix in (" 600 ml Bottle",):
			if name.endswith(suffix):
				brand = name[: -len(suffix)].strip()
				break

	if not brand:
		companies = frappe.get_all("Company", pluck="name")
		brand = companies[0] if len(companies) == 1 else None
	if not brand:
		return

	try:
		from neoaqua.setup.brand import set_brand

		set_brand(brand)
		# stamp the Brand on the finished goods that predate the field
		for item in frappe.get_all("Item", filters={"item_code": ["like", "FG-%"]}, pluck="name"):
			if not frappe.db.get_value("Item", item, "brand"):
				frappe.db.set_value("Item", item, "brand", brand, update_modified=False)
		frappe.db.commit()
	except Exception:
		frappe.log_error(frappe.get_traceback(), "NeoAqua v15.6.0 brand backfill")
