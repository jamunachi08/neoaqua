# Copyright (c) 2026, Neotec Integrated Solutions
"""v15.5.0 - rename the product brand from Nova Water to Neo Aqua.

Item CODES are unchanged, so no transaction, BOM or batch is affected. Only the
display name moves, which is what appears on invoices, receipts and reports.
"""

import frappe


def execute():
	for item in frappe.get_all(
		"Item",
		filters={"item_name": ["like", "Nova Water%"]},
		fields=["name", "item_name", "description"],
	):
		new_name = item.item_name.replace("Nova Water", "Neo Aqua")
		values = {"item_name": new_name}
		if item.description and "Nova Water" in item.description:
			values["description"] = item.description.replace("Nova Water", "Neo Aqua")
		frappe.db.set_value("Item", item.name, values, update_modified=False)

	frappe.db.commit()
