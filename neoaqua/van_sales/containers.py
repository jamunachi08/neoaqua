# Copyright (c) 2026, Neotec Integrated Solutions
"""Returnable container balance helpers and the Customer dashboard override."""

import frappe
from frappe.utils import flt


def rebuild_container_balances():
	"""Nightly: refresh the running balance stamped on each ledger entry so the
	report reads a single column instead of recomputing."""
	customers = frappe.get_all(
		"Container Ledger Entry", filters={"docstatus": 1}, pluck="customer", distinct=True
	)
	for customer in customers:
		bal = 0
		rows = frappe.get_all(
			"Container Ledger Entry",
			filters={"customer": customer, "docstatus": 1},
			fields=["name", "entry_type", "qty"],
			order_by="posting_date asc, creation asc",
		)
		for r in rows:
			if r.entry_type in ("Issue (Full Out)", "Lost / Damaged", "Opening Balance"):
				bal += flt(r.qty)
			elif r.entry_type == "Return (Empty In)":
				bal -= flt(r.qty)
			frappe.db.set_value("Container Ledger Entry", r.name, "balance_qty", bal, update_modified=False)
	frappe.db.commit()


def customer_dashboard(data):
	data["transactions"].append(
		{"label": "NeoAqua", "items": ["Container Ledger Entry", "Salesman Check In", "Geofence Zone"]}
	)
	return data
